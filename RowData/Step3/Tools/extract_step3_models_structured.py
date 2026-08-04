from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
CORE_BLOCKS_PATH = STEP3_DIR / "Data" / "step3_core_blocks.jsonl"


THRESH_TOKEN_RE = re.compile(
    r"(?:>=|≤|>=|<=|>|<|≥)\s*[0-9]+(?:\.[0-9]+)?\s*(?:%|分|次/年|小时|天|月|年)?|"
    r"[0-9]+%|<\s*[0-9]+%|>\s*[0-9]+%|"
    r"\b[0-9]+(?:\.[0-9]+)?\b\s*(?:%|分|次/年|小时|天|月|年)",
    re.IGNORECASE,
)
ROLE_RE = re.compile(r"\b([A-Z])\-([A-Za-z]{2,12})\b")


@dataclass
class DimRow:
    name: str
    text: str
    thresholds: list[str]
    roles: list[str]
    bullets: list[str]
    source_num: str | None = None


@dataclass
class LabelSpan:
    label: str
    start: int
    end: int
    source_num: str | None = None


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            yield json.loads(s)


def _fix_vertical_cjk(text: str) -> str:
    """Fix common PDF-extracted vertical text.

    1) Merge runs of single CJK chars: 失\n能 -> 失能
    2) Merge short CJK lines (<=2 chars) when they likely form a label.
    """

    lines = text.splitlines()

    def is_single_cjk(line: str) -> bool:
        t = line.strip()
        return len(t) == 1 and "\u4e00" <= t <= "\u9fff"

    def is_short_cjk(line: str) -> bool:
        t = line.strip()
        if not t:
            return False
        if len(t) > 2:
            return False
        return all("\u4e00" <= ch <= "\u9fff" for ch in t)

    out: list[str] = []
    buf = ""

    # Pass 1: merge single-cjk runs.
    temp: list[str] = []
    for raw in lines:
        if is_single_cjk(raw):
            buf += raw.strip()
            continue
        if buf:
            temp.append(buf)
            buf = ""
        temp.append(raw)
    if buf:
        temp.append(buf)

    # Pass 2: merge short-cjk labels like 地缘\n政治\n奇点.
    i = 0
    while i < len(temp):
        cur = temp[i].strip()
        if not cur:
            out.append(temp[i])
            i += 1
            continue

        if is_short_cjk(cur):
            merged = cur
            j = i + 1
            while j < len(temp) and is_short_cjk(temp[j].strip()):
                merged += temp[j].strip()
                j += 1
            # If next line completes a label, merge it too.
            if j < len(temp):
                nxt = temp[j].strip()
                if nxt in {"奇点", "窗口", "崩溃"}:
                    merged += nxt
                    j += 1
            out.append(merged)
            i = j
            continue

        out.append(temp[i])
        i += 1

    return "\n".join(out)


def _compact_with_map(text: str) -> tuple[str, list[int]]:
    """Return (compact_text, index_map).

    compact_text is the original text with all whitespace removed.
    index_map[i] gives the original index of compact_text[i].
    """
    compact_chars: list[str] = []
    index_map: list[int] = []
    for idx, ch in enumerate(text):
        if ch.isspace():
            continue
        compact_chars.append(ch)
        index_map.append(idx)
    return "".join(compact_chars), index_map


def _first_span(text: str, pattern: re.Pattern[str]) -> tuple[int, int] | None:
    m = pattern.search(text)
    if not m:
        return None
    return m.start(), m.end()


def _slice_by_spans(text: str, spans: list[LabelSpan]) -> list[DimRow]:
    spans_sorted = sorted(spans, key=lambda s: s.start)
    rows: list[DimRow] = []
    for i, sp in enumerate(spans_sorted):
        end = spans_sorted[i + 1].start if i + 1 < len(spans_sorted) else len(text)
        seg = text[sp.start:end].strip()
        rows.append(
            DimRow(
                name=sp.label,
                text=seg,
                thresholds=_extract_thresholds(seg),
                roles=_extract_roles(seg),
                bullets=_extract_bullets(seg),
                source_num=sp.source_num,
            )
        )
    return rows


def _extract_thresholds(text: str) -> list[str]:
    found = THRESH_TOKEN_RE.findall(text)
    uniq: list[str] = []
    seen: set[str] = set()
    for t in found:
        s = t.strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _extract_roles(text: str) -> list[str]:
    roles = ROLE_RE.findall(text)
    uniq: list[str] = []
    seen: set[str] = set()
    for a, b in roles:
        r = f"{a}-{b}"
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def _extract_bullets(text: str, max_items: int = 120) -> list[str]:
    bullets: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("•") or s.startswith("-"):
            bullets.append(s[:220])
            if len(bullets) >= max_items:
                break
    return bullets


def _slice_by_labels_compact(text: str, labels: list[str], source_num: str | None = None) -> list[DimRow]:
    # Search labels in compact (no whitespace), then slice original by mapped indices.
    compact, index_map = _compact_with_map(text)

    positions: list[tuple[int, str]] = []
    for lab in labels:
        if not lab:
            continue
        lab_c = re.sub(r"\s+", "", lab)
        idx = compact.find(lab_c)
        if idx >= 0:
            positions.append((idx, lab))
    positions.sort(key=lambda x: x[0])

    rows: list[DimRow] = []
    for i, (cpos, lab) in enumerate(positions):
        cend = positions[i + 1][0] if i + 1 < len(positions) else len(compact)
        start = index_map[cpos] if cpos < len(index_map) else 0
        end = index_map[cend - 1] + 1 if cend - 1 < len(index_map) and cend > 0 else len(text)
        seg = text[start:end].strip()
        rows.append(
            DimRow(
                name=lab,
                text=seg,
                thresholds=_extract_thresholds(seg),
                roles=_extract_roles(seg),
                bullets=_extract_bullets(seg),
                source_num=source_num,
            )
        )
    return rows


def _build_spans_by_patterns(
    text: str,
    label_to_patterns: dict[str, list[re.Pattern[str]]],
    source_num: str | None = None,
) -> list[LabelSpan]:
    spans: list[LabelSpan] = []
    for label, patterns in label_to_patterns.items():
        for pat in patterns:
            span = _first_span(text, pat)
            if span:
                spans.append(LabelSpan(label=label, start=span[0], end=span[1], source_num=source_num))
                break
    # De-dup by label, keep earliest.
    by_label: dict[str, LabelSpan] = {}
    for sp in sorted(spans, key=lambda s: s.start):
        if sp.label not in by_label:
            by_label[sp.label] = sp
    return list(by_label.values())


def _infer_labels_regex_compact(text: str, pattern: re.Pattern[str], max_labels: int) -> list[str]:
    compact, _ = _compact_with_map(text)
    labels: list[str] = []
    seen: set[str] = set()
    for m in pattern.finditer(compact):
        lab = m.group(0)
        if lab in seen:
            continue
        seen.add(lab)
        labels.append(lab)
        if len(labels) >= max_labels:
            break
    return labels


def _pick_model_block(records: list[dict[str, Any]], major: str, want_in_title: str) -> dict[str, Any] | None:
    for r in records:
        if str(r.get("major")) != str(major):
            continue
        title = str(r.get("title") or "")
        if want_in_title in title:
            return r
    return None


def main() -> int:
    if not CORE_BLOCKS_PATH.exists():
        raise SystemExit(f"Missing: {CORE_BLOCKS_PATH}")

    records = list(_read_jsonl(CORE_BLOCKS_PATH))

    # Target the 7 core model tables.
    targets = [
        (
            "1",
            "八维状态模型",
            "fixed",
            ["失能", "失智", "失控", "失联", "失心", "失信", "失和", "失格"],
        ),
        (
            "2",
            "崩溃维度",
            "fixed",
            ["价值认同崩溃", "信任纽带崩溃", "共同叙事崩溃", "规则共识崩溃"],
        ),
        (
            "3",
            "决策偏差模型",
            "fixed",
            ["战略方向误判", "权力结构扭曲", "风险认知偏差", "资源配置失衡", "时机把握失衡"],
        ),
        (
            "4",
            "窗口模型",
            "fixed",
            ["代际传承窗口", "战略机遇窗口", "资产重构窗口", "关系修复窗口"],
        ),
        (
            "5",
            "五维分类模型",
            "fixed",
            ["流动性枯竭奇点", "资产价值湮灭奇点", "债务螺旋奇点", "资产负债表击穿奇点", "资本成本失控奇点"],
        ),
        (
            "6",
            "六维分类模型",
            "fixed",
            ["核心技术断层", "数字资产湮灭", "技术代际落差", "技术范式颠覆", "系统架构崩溃", "技术伦理失控"],
        ),
        (
            "7",
            "八大类别模型",
            "regex",
            "EVENT",
        ),
    ]

    models: list[dict[str, Any]] = []

    for major, title_key, mode, extra in targets:
        block = _pick_model_block(records, major, title_key)
        if not block:
            models.append(
                {
                    "major": major,
                    "title_key": title_key,
                    "error": "block_not_found",
                }
            )
            continue

        raw_text = str(block.get("text") or "")
        text = _fix_vertical_cjk(raw_text)

        if mode == "fixed":
            labels = list(extra)  # type: ignore[arg-type]
        elif mode == "regex" and str(extra) == "EVENT":
            # Events: pick 8 short labels ending with “奇点”, excluding the 7 core singularities.
            pat = re.compile(r"[\u4e00-\u9fff]{2,8}奇点")
            labels = _infer_labels_regex_compact(text, pat, max_labels=12)
            exclude = {
                "事件奇点",
                "人物奇点",
                "时间奇点",
                "财务奇点",
                "技术奇点",
                "认知/文化奇点",
                "认知奇点",
                "文化奇点",
                "权力/决策奇点",
                "决策奇点",
                "权力奇点",
            }
            labels = [l for l in labels if l not in exclude][:8]
        else:
            labels = []

        # Robust slicing for fixed-models with messy table column interleaving.
        rows: list[DimRow]
        row_sources: dict[str, str] = {}
        if mode == "fixed" and major in {"2", "4", "5", "6"}:
            label_to_patterns: dict[str, list[re.Pattern[str]]] = {}

            if major == "2":
                label_to_patterns = {
                    "价值认同崩溃": [re.compile(r"价值\s*认同\s*崩溃")],
                    "信任纽带崩溃": [re.compile(r"信任\s*纽带\s*崩溃")],
                    "共同叙事崩溃": [re.compile(r"共同\s*叙事\s*崩溃"), re.compile(r"叙事\s*认同\s*崩溃")],
                    "规则共识崩溃": [re.compile(r"规则\s*共识\s*崩溃")],
                }

            if major == "4":
                label_to_patterns = {
                    "代际传承窗口": [re.compile(r"代际传\s*承窗口")],
                    # Allow interleaving between “战略机” and “遇窗口”.
                    "战略机遇窗口": [re.compile(r"战略机[\s\S]{0,400}?遇窗口")],
                    "资产重构窗口": [re.compile(r"资产重\s*构窗口"), re.compile(r"资产重构\s*窗口")],
                    "关系修复窗口": [re.compile(r"关系修\s*复窗口"), re.compile(r"关系修复\s*窗口")],
                }

            if major == "5":
                label_to_patterns = {
                    "流动性枯竭奇点": [re.compile(r"流动性[\s\S]{0,40}?枯竭奇\s*点")],
                    "资产价值湮灭奇点": [re.compile(r"资产价[\s\S]{0,40}?值湮灭\s*奇点")],
                    "债务螺旋奇点": [re.compile(r"债务螺\s*旋\s*奇点")],
                    "资产负债表击穿奇点": [re.compile(r"资产负[\s\S]{0,20}?债表击[\s\S]{0,10}?穿奇点")],
                    "资本成本失控奇点": [re.compile(r"资本成[\s\S]{0,20}?本失控\s*奇点")],
                }

            if major == "6":
                label_to_patterns = {
                    "核心技术断层": [re.compile(r"核心[\s\S]{0,20}?技术[\s\S]{0,20}?断层")],
                    "数字资产湮灭": [re.compile(r"数字[\s\S]{0,10}?资产[\s\S]{0,10}?湮灭")],
                    "技术代际落差": [re.compile(r"技术[\s\S]{0,10}?代际[\s\S]{0,10}?落差")],
                    "技术范式颠覆": [re.compile(r"技术[\s\S]{0,10}?范式[\s\S]{0,10}?颠覆")],
                    "系统架构崩溃": [re.compile(r"系统[\s\S]{0,10}?架构[\s\S]{0,10}?崩溃")],
                    "技术伦理失控": [re.compile(r"技术[\s\S]{0,10}?伦理[\s\S]{0,10}?失控")],
                }

            spans = _build_spans_by_patterns(text, label_to_patterns, source_num=str(block.get("num")))

            # For time windows: if some labels missing in 4.3, fall back to 4.6.1 (where window types are explicit).
            if major == "4":
                have = {sp.label for sp in spans}
                missing = [lab for lab in labels if lab not in have]
                if missing:
                    fallback = next(
                        (
                            r
                            for r in records
                            if str(r.get("major")) == "4" and str(r.get("num")) == "4.6.1"
                        ),
                        None,
                    )
                    if fallback:
                        fb_text = _fix_vertical_cjk(str(fallback.get("text") or ""))
                        fb_patterns = {lab: label_to_patterns[lab] for lab in missing if lab in label_to_patterns}
                        fb_spans = _build_spans_by_patterns(
                            fb_text,
                            fb_patterns,
                            source_num=str(fallback.get("num")),
                        )
                        # Convert fallback spans into the current text space by appending as separate pseudo-rows.
                        # We'll slice fallback separately and store its preview; keep main rows from main text.
                        rows = _slice_by_spans(text, spans)
                        for sp in fb_spans:
                            seg = fb_text[sp.start :].strip()
                            rows.append(
                                DimRow(
                                    name=f"{sp.label} (from {sp.source_num})",
                                    text=seg,
                                    thresholds=_extract_thresholds(seg),
                                    roles=_extract_roles(seg),
                                    bullets=_extract_bullets(seg),
                                    source_num=sp.source_num,
                                )
                            )
                        # Keep in a stable order: main rows first, then fallback rows.
                        row_sources = {r.name: str(block.get("num")) for r in rows}
                        # Done.
                        pass
                    else:
                        rows = _slice_by_spans(text, spans)
                else:
                    rows = _slice_by_spans(text, spans)
            else:
                rows = _slice_by_spans(text, spans)
        else:
            # For person/decision/event: compact slicing works sufficiently.
            rows = _slice_by_labels_compact(text, labels, source_num=str(block.get("num")))

        models.append(
            {
                "major": major,
                "num": block.get("num"),
                "title": block.get("title"),
                "start_line": block.get("start_line"),
                "end_line": block.get("end_line"),
                "label_mode": mode,
                "labels": labels,
                "row_count": len(rows),
                "rows": [
                    {
                        "name": r.name,
                        "thresholds": r.thresholds,
                        "roles": r.roles,
                        "bullets": r.bullets,
                        "source_num": r.source_num,
                        "text_preview": r.text[:600],
                    }
                    for r in rows
                ],
                "notes": [
                    "This is a first-pass structure: rows are sliced by label occurrence.",
                    "Next refinement will map cells into columns (definition / indicators / thresholds / roles).",
                ],
            }
        )

    out = {
        "source": str(CORE_BLOCKS_PATH),
        "models": models,
    }

    out_path = STEP3_DIR / "Data" / "step3_models_structured.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))

    # Basic stats.
    ok = [m for m in models if isinstance(m, dict) and m.get("error") is None]
    print(f"models={len(models)}")
    for m in models:
        if "error" in m:
            print(f"major={m.get('major')} status=error {m.get('error')}")
        else:
            print(f"major={m.get('major')} rows={m.get('row_count')} labels={len(m.get('labels') or [])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
