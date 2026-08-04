from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
IN_PATH = STEP3_DIR / "Data" / "step3_models_structured.json"
OUT_SCHEMA_PATH = STEP3_DIR / "Data" / "step3_models_schema.json"
OUT_REPORT_PATH = STEP3_DIR / "Data" / "step3_models_quality_report.md"


PAGE_RE = re.compile(r"=+\s*PAGE\s*\d+/\d+\s*=+", re.IGNORECASE)
ROLE_MARKER_RE = re.compile(
    r"(根源性初始点|引爆点|放大器|核心放大器)\s*[（(]\s*([A-Z]\-[A-Za-z]{2,12})\s*[）)]"
)
THRESH_TOKEN_RE = re.compile(
    r"(?:>=|≤|>=|<=|>|<|≥)\s*[0-9]+(?:\.[0-9]+)?\s*(?:%|分|次/年|小时|天|月|年)?|"
    r"[0-9]+%|<\s*[0-9]+%|>\s*[0-9]+%|"
    r"\b[0-9]+(?:\.[0-9]+)?\b\s*(?:%|分|次/年|小时|天|月|年)|"
    r"(?:>=|≤|>=|<=|>|<|≥)\s*±\s*[0-9]+\s*σ|"
    r"±\s*[0-9]+\s*σ",
    re.IGNORECASE,
)


@dataclass
class Indicator:
    name: str
    indicator_key: str
    indicator_id: str
    thresholds: list[str]
    evidence: str | None = None


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if PAGE_RE.search(s):
            continue
        # Drop obvious separator lines
        if set(s) <= {"=", "-", "_"}:
            continue
        lines.append(s)
    return lines


def _is_cjkish(s: str) -> bool:
    return re.search(r"[\u4e00-\u9fff]", s or "") is not None


def _merge_broken_lines(lines: list[str], *, strip_bullet_prefix: bool = False) -> list[str]:
    """Merge very short adjacent lines caused by PDF column/line breaks.

    Examples: "疗资源响" + "应时效" -> "疗资源响应时效"
    "决策偏" + "执指数" -> "决策偏执指数"
    """

    merged: list[str] = []
    i = 0
    while i < len(lines):
        raw_cur = lines[i].strip()
        if not raw_cur:
            i += 1
            continue

        cur = raw_cur
        if strip_bullet_prefix and (raw_cur.startswith("•") or raw_cur.startswith("-")):
            candidate = raw_cur.lstrip("•-").strip()
            if candidate and _is_cjkish(candidate) and len(candidate) <= 5:
                cur = candidate

        if (
            len(cur) <= 4
            and _is_cjkish(cur)
            and not cur.startswith("•")
            and not cur.startswith("-")
            and not ROLE_MARKER_RE.search(cur)
            and not _looks_like_threshold_line(cur)
        ):
            combined = cur
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if (
                    not nxt
                    or nxt.startswith("•")
                    or nxt.startswith("-")
                    or ROLE_MARKER_RE.search(nxt)
                    or _looks_like_threshold_line(nxt)
                ):
                    break
                if not _is_cjkish(nxt):
                    break
                if len(nxt) > 4:
                    break
                if len(combined) + len(nxt) > 14:
                    break
                combined += nxt
                j += 1

            if combined != cur:
                merged.append(combined)
                i = j
                continue

        merged.append(cur)
        i += 1

    return merged


def _normalize_indicator_name(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return ""

    # Normalize punctuation and whitespace.
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    s = s.replace(":", "").replace("：", "")
    s = s.strip("-—_·•")

    # Common OCR/break artifacts.
    s = s.replace("/", "")
    s = re.sub(r"\(\s*\)", "", s)
    return s


def _indicator_key(name: str) -> str:
    # Key is the normalized string used for identity and matching.
    return _normalize_indicator_name(name)


def _is_valid_indicator_key(key: str) -> bool:
    k = (key or "").strip()
    if not k:
        return False
    # Drop common OCR fragments like a single "率" or "度".
    if len(k) < 4:
        return False
    # Must contain at least one metric-ish token.
    metric_tokens = [
        "率",
        "度",
        "值",
        "指数",
        "净值",
        "覆盖",
        "偏差",
        "风险",
        "关联",
        "时效",
        "账户",
        "匹配",
        "渗透",
        "通过率",
        "成功率",
        "活跃度",
    ]
    return any(t in k for t in metric_tokens)


def _indicator_id(major: str, row_name: str, key: str) -> str:
    seed = f"m={major}|row={_normalize_indicator_name(row_name)}|k={key}".encode("utf-8")
    digest = hashlib.sha1(seed).hexdigest()[:12]
    return f"m{major}_{digest}"


def _looks_like_threshold_line(s: str) -> bool:
    return bool(THRESH_TOKEN_RE.search(s))


def _looks_like_indicator_name(s: str) -> bool:
    # Heuristics: metric-like label (often ends with 率/度/值/指数...), not a role marker/threshold.
    ss = s.strip()
    if not ss:
        return False

    # Allow bullet lines, but evaluate their content.
    if ss.startswith("•") or ss.startswith("-"):
        ss = ss.lstrip("•-").strip()
        if not ss:
            return False

    if ROLE_MARKER_RE.search(ss):
        return False
    if _looks_like_threshold_line(ss):
        return False

    # Too long -> likely narrative.
    if len(ss) > 26:
        return False

    # Needs some CJK or common indicator nouns.
    if any(p in ss for p in ["，", "、", "。", "；", ",", ";"]):
        return False
    if any(bad in ss for bad in ["无法", "导致", "迅速", "长期", "严重", "频发", "消失"]):
        return False

    if re.search(r"[\u4e00-\u9fff]", ss) is None:
        return False

    if any(
        k in ss
        for k in [
            "率",
            "度",
            "值",
            "指数",
            "净值",
            "覆盖",
            "偏差",
            "风险",
            "关联",
            "时效",
            "账户",
            "匹配",
            "渗透",
            "精准",
            "通过率",
            "成功率",
            "活跃度",
        ]
    ):
        return True
    # Without metric-ish tokens, treat as narrative.
    return False


def _extract_definition(row_name: str, row_text: str) -> str | None:
    lines = _merge_broken_lines(_clean_lines(row_text), strip_bullet_prefix=False)
    if not lines:
        return None

    # Remove leading row label line if present.
    if lines and lines[0].replace(" ", "") == row_name.replace(" ", ""):
        lines = lines[1:]

    collected: list[str] = []
    for s in lines:
        if s.startswith("•") or s.startswith("-"):
            break
        if ROLE_MARKER_RE.search(s):
            break
        if _looks_like_threshold_line(s):
            break
        # stop at propagation headers
        if "传导" in s or "放大" in s:
            break
        collected.append(s)
        if len("".join(collected)) >= 120:
            break

    text = "".join(collected).strip()
    return text or None


def _extract_role_markers(row_text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in ROLE_MARKER_RE.finditer(row_text or ""):
        out.append({"role_cn": m.group(1), "role_code": m.group(2)})
    return out


def _extract_propagation_notes(row_text: str, max_items: int = 6) -> list[str]:
    notes: list[str] = []
    for s in _clean_lines(row_text):
        if any(k in s for k in ["传导", "放大", "非线性", "加速", "系数", "引爆"]):
            if s not in notes:
                notes.append(s[:220])
        if len(notes) >= max_items:
            break
    return notes


def _extract_indicator_pairs(
    row_text: str,
    *,
    major: str,
    row_name: str,
    max_items: int = 12,
) -> list[Indicator]:
    lines = _merge_broken_lines(_clean_lines(row_text), strip_bullet_prefix=True)
    indicators: list[Indicator] = []
    seen: set[str] = set()

    for i, s in enumerate(lines):
        if not _looks_like_indicator_name(s):
            continue
        # Look ahead for thresholds within next few lines.
        window = "\n".join(lines[i : i + 6])
        ths = [t.strip() for t in THRESH_TOKEN_RE.findall(window) if t.strip()]
        th_uniq: list[str] = []
        for t in ths:
            if t not in th_uniq:
                th_uniq.append(t)

        if not th_uniq:
            continue

        name_raw = re.sub(r"[：:\s]+$", "", s)
        # If the next line is a bracketed annotation, keep it with the name.
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt.startswith("(") or nxt.startswith("（") or "分制" in nxt or "标准差" in nxt:
                if len(nxt) <= 16:
                    name_raw = f"{name_raw}{nxt}"

        key = _indicator_key(name_raw)
        if not _is_valid_indicator_key(key):
            continue
        if key in seen:
            continue
        seen.add(key)

        indicators.append(
            Indicator(
                name=_normalize_indicator_name(name_raw),
                indicator_key=key,
                indicator_id=_indicator_id(major, row_name, key),
                thresholds=th_uniq,
                evidence=window[:260],
            )
        )
        if len(indicators) >= max_items:
            break

    return indicators


def main() -> int:
    if not IN_PATH.exists():
        raise SystemExit(f"Missing input: {IN_PATH}")

    data = _read_json(IN_PATH)
    models_in = data.get("models") or []

    schema_models: list[dict[str, Any]] = []
    report_lines: list[str] = []

    report_lines.append(f"# Step3 模型抽取质量报告\n")
    report_lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    report_lines.append(f"- Input: {IN_PATH}\n")
    report_lines.append(f"- Output: {OUT_SCHEMA_PATH}\n")

    for model in models_in:
        major = str(model.get("major") or "")
        num = str(model.get("num") or "")
        title = str(model.get("title") or "")
        labels = model.get("labels") or []
        rows_in = model.get("rows") or []

        report_lines.append(f"\n## major={major} num={num} {title}\n")
        report_lines.append(f"- labels={len(labels)} rows={len(rows_in)}\n")

        schema_rows: list[dict[str, Any]] = []
        for r in rows_in:
            name = str(r.get("name") or "")
            text_preview = str(r.get("text_preview") or "")
            row_source_num = r.get("source_num")

            definition = _extract_definition(name, text_preview)
            indicators = _extract_indicator_pairs(text_preview, major=major, row_name=name)
            role_markers = _extract_role_markers(text_preview)
            propagation = _extract_propagation_notes(text_preview)

            schema_row = {
                "name": name,
                "source_num": row_source_num,
                "definition": definition,
                "indicators": [
                    {
                        "indicator_id": it.indicator_id,
                        "indicator_key": it.indicator_key,
                        "name": it.name,
                        "thresholds": it.thresholds,
                        "evidence": it.evidence,
                    }
                    for it in indicators
                ],
                "thresholds": r.get("thresholds") or [],
                "roles": r.get("roles") or [],
                "role_markers": role_markers,
                "propagation": propagation,
                "bullets": r.get("bullets") or [],
                "raw_preview": text_preview,
            }
            schema_rows.append(schema_row)

            report_lines.append(
                f"- {name}: def={'Y' if definition else 'N'} "
                f"ind={len(indicators)} th={len(schema_row['thresholds'])} roles={schema_row['roles']}"
                + (f" src={row_source_num}" if row_source_num else "")
                + "\n"
            )

        schema_models.append(
            {
                "major": major,
                "num": num,
                "title": title,
                "start_line": model.get("start_line"),
                "end_line": model.get("end_line"),
                "label_mode": model.get("label_mode"),
                "labels": labels,
                "rows": schema_rows,
            }
        )

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(IN_PATH),
        "models": schema_models,
        "notes": [
            "This is a heuristic columnization pass.",
            "Rows retain raw_preview; indicators are paired with nearby threshold tokens when possible.",
        ],
    }

    _write_json(OUT_SCHEMA_PATH, out)
    _write_text(OUT_REPORT_PATH, "".join(report_lines))

    print(OUT_SCHEMA_PATH)
    print(OUT_REPORT_PATH)
    print(f"models={len(schema_models)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
