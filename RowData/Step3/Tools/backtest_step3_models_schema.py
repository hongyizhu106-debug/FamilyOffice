from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
SCHEMA_PATH = STEP3_DIR / "Data" / "step3_models_schema.json"
STRUCTURED_PATH = STEP3_DIR / "Data" / "step3_models_structured.json"
OUT_REPORT = STEP3_DIR / "Data" / "step3_models_schema_backtest.md"


THRESH_TOKEN_RE = re.compile(
    r"(?:>=|≤|>=|<=|>|<|≥)\s*[0-9]+(?:\.[0-9]+)?\s*(?:%|分|次/年|小时|天|月|年)?|"
    r"[0-9]+%|<\s*[0-9]+%|>\s*[0-9]+%|"
    r"\b[0-9]+(?:\.[0-9]+)?\b\s*(?:%|分|次/年|小时|天|月|年)|"
    r"(?:>=|≤|>=|<=|>|<|≥)\s*±\s*[0-9]+\s*σ|"
    r"±\s*[0-9]+\s*σ",
    re.IGNORECASE,
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _collect_thresholds(text: str) -> list[str]:
    found = [t.strip() for t in THRESH_TOKEN_RE.findall(text or "") if t.strip()]
    out: list[str] = []
    for t in found:
        if t not in out:
            out.append(t)
    return out


def main() -> int:
    if not SCHEMA_PATH.exists():
        raise SystemExit(f"Missing: {SCHEMA_PATH}")
    if not STRUCTURED_PATH.exists():
        raise SystemExit(f"Missing: {STRUCTURED_PATH}")

    schema = _read_json(SCHEMA_PATH)
    structured = _read_json(STRUCTURED_PATH)

    # Build lookup from structured: (major,num,row_name)-> thresholds extracted earlier
    structured_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for m in structured.get("models") or []:
        major = str(m.get("major") or "")
        num = str(m.get("num") or "")
        for r in m.get("rows") or []:
            key = (major, num, str(r.get("name") or ""))
            structured_lookup[key] = r

    errors: list[str] = []
    warns: list[str] = []

    indicator_ids: list[str] = []
    indicator_keys: list[str] = []

    model_counts = Counter()

    for m in schema.get("models") or []:
        major = str(m.get("major") or "")
        num = str(m.get("num") or "")
        title = str(m.get("title") or "")

        rows = m.get("rows") or []
        model_counts[major] += len(rows)

        for row in rows:
            row_name = str(row.get("name") or "")
            src = row.get("source_num")
            if not src:
                errors.append(f"missing source_num: major={major} num={num} row={row_name}")

            raw_preview = str(row.get("raw_preview") or "")
            th_in_preview = set(_collect_thresholds(raw_preview))
            th_declared = set([t for t in (row.get("thresholds") or []) if isinstance(t, str)])
            missing_tokens = sorted([t for t in th_declared if t not in th_in_preview])
            if missing_tokens:
                warns.append(
                    f"thresholds not found in raw_preview: major={major} num={num} row={row_name} missing={missing_tokens}"
                )

            inds = row.get("indicators") or []
            for ind in inds:
                iid = str(ind.get("indicator_id") or "")
                ikey = str(ind.get("indicator_key") or "")
                iname = str(ind.get("name") or "")

                if not iid:
                    errors.append(f"missing indicator_id: major={major} num={num} row={row_name} indicator={iname}")
                if not ikey:
                    errors.append(f"missing indicator_key: major={major} num={num} row={row_name} indicator={iname}")

                if iid:
                    indicator_ids.append(iid)
                if ikey:
                    indicator_keys.append(ikey)

                # Evidence sanity: thresholds should appear in evidence window
                ev = str(ind.get("evidence") or "")
                th_ind = [t for t in (ind.get("thresholds") or []) if isinstance(t, str)]
                if th_ind and ev:
                    ev_tokens = set(_collect_thresholds(ev))
                    miss = [t for t in th_ind if t not in ev_tokens]
                    if miss:
                        warns.append(
                            f"indicator thresholds not found in evidence: major={major} num={num} row={row_name} indicator={iname} missing={miss}"
                        )

            # Cross-check with structured rows when names match exactly
            srow = structured_lookup.get((major, num, row_name))
            if srow:
                s_th = set([t for t in (srow.get("thresholds") or []) if isinstance(t, str)])
                if th_declared and not s_th:
                    warns.append(f"schema thresholds exist but structured thresholds empty: major={major} num={num} row={row_name}")
            else:
                # Expected for fallback rows renamed with '(from X)'
                if "(from" not in row_name:
                    warns.append(f"row not found in structured lookup: major={major} num={num} row={row_name}")

    # Duplicate ID/key checks
    dup_ids = [k for k, c in Counter(indicator_ids).items() if c > 1]
    dup_keys = [k for k, c in Counter(indicator_keys).items() if c > 3]  # keys can repeat across models, but flag heavy repeats

    if dup_ids:
        errors.append(f"duplicate indicator_id(s): {dup_ids[:20]}")
    if dup_keys:
        warns.append(f"highly repeated indicator_key(s) (c>3): {dup_keys[:20]}")

    lines: list[str] = []
    lines.append("# Step3 models_schema 回测报告\n")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    lines.append(f"- Schema: {SCHEMA_PATH}\n")
    lines.append(f"- Structured: {STRUCTURED_PATH}\n")
    lines.append("\n## Summary\n")
    lines.append(f"- Models: {len(schema.get('models') or [])}\n")
    lines.append(f"- Rows by major: {dict(model_counts)}\n")
    lines.append(f"- Indicators: {len(indicator_ids)}\n")
    lines.append(f"- Errors: {len(errors)}\n")
    lines.append(f"- Warnings: {len(warns)}\n")

    if errors:
        lines.append("\n## Errors\n")
        for e in errors[:200]:
            lines.append(f"- {e}\n")

    if warns:
        lines.append("\n## Warnings\n")
        for w in warns[:400]:
            lines.append(f"- {w}\n")

    _write_text(OUT_REPORT, "".join(lines))

    print(OUT_REPORT)
    print(f"errors={len(errors)} warnings={len(warns)}")

    # Treat errors as failure; warnings are OK.
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
