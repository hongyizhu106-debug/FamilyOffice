from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
CORE_BLOCKS_PATH = STEP3_DIR / "Data" / "step3_core_blocks.jsonl"


ROLE_RE = re.compile(r"\b([A-Z])\-([A-Za-z]{2,12})\b")

# Examples:
#   人物奇点（失智）→ 决策奇点（战略误判）
#   事件奇点（监管规则剧变）→ 财务奇点（商业模式失效）
EDGE_RE = re.compile(
    r"(?P<src>[\u4e00-\u9fff/]+)奇点\s*（(?P<src_detail>[^）]{0,80})）\s*→\s*"
    r"(?P<dst>[\u4e00-\u9fff/]+)奇点\s*（(?P<dst_detail>[^）]{0,80})）",
    re.MULTILINE,
)

EDGE_NO_PAREN_RE = re.compile(
    r"(?P<src>[\u4e00-\u9fff/]+)奇点\s*→\s*(?P<dst>[\u4e00-\u9fff/]+)奇点",
    re.MULTILINE,
)


def _normalize_singularity_name(name: str) -> str:
    n = name.strip()
    # Common abbreviations in extracted text.
    if n == "决策":
        return "权力/决策"
    if n == "权力":
        return "权力/决策"
    if n == "认知":
        return "认知/文化"
    if n == "文化":
        return "认知/文化"
    return n

# Capture K variants: Kₘ=1, K1=0.7, K₁=0.78; K₂=1.56
K_ASSIGN_RE = re.compile(
    r"(?:(?:\bK\b|K[₀-₉]+|K\d+|K[ₘ])\s*=\s*[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)

# Capture multiplier forms like "×1.8" or "x1.8" occasionally.
MULT_RE = re.compile(r"[×xX]\s*(?P<mul>[0-9]+(?:\.[0-9]+)?)")

# Threshold-ish tokens; we keep them as candidates (don’t over-parse yet).
THRESH_TOKEN_RE = re.compile(
    r"(?:>=|≤|>=|<=|>|<|≥)\s*[0-9]+(?:\.[0-9]+)?\s*(?:%|分|次/年|小时|天|月|年)?|"
    r"[0-9]+%|<\s*[0-9]+%|>\s*[0-9]+%|"
    r"\b[0-9]+(?:\.[0-9]+)?\b\s*(?:%|分|次/年|小时|天|月|年)",
    re.IGNORECASE,
)


@dataclass
class Edge:
    src: str
    dst: str
    src_detail: str
    dst_detail: str
    k: list[str]
    multipliers: list[float]
    context: str


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            yield json.loads(s)


def _fix_vertical_cjk(text: str) -> str:
    """Fix common PDF-extracted vertical text like '失\n能' -> '失能'.

    Heuristic: merge consecutive lines that are single CJK char.
    """
    lines = text.splitlines()
    out: list[str] = []
    buffer = ""

    def is_single_cjk(line: str) -> bool:
        t = line.strip()
        return len(t) == 1 and "\u4e00" <= t <= "\u9fff"

    for raw in lines:
        if is_single_cjk(raw):
            buffer += raw.strip()
            continue
        if buffer:
            out.append(buffer)
            buffer = ""
        out.append(raw)

    if buffer:
        out.append(buffer)

    return "\n".join(out)


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


def _extract_edges(text: str) -> list[Edge]:
    edges: list[Edge] = []

    def add_edge(start: int, end: int, src: str, dst: str, src_detail: str, dst_detail: str) -> None:
        post = text[end : end + 800]
        pre = text[max(0, start - 250) : start]
        context = (pre + text[start:end] + post[:250]).strip()

        k = K_ASSIGN_RE.findall(post)
        multipliers = [float(x) for x in MULT_RE.findall(post)]

        edges.append(
            Edge(
                src=_normalize_singularity_name(src),
                dst=_normalize_singularity_name(dst),
                src_detail=src_detail,
                dst_detail=dst_detail,
                k=[kk.strip() for kk in k],
                multipliers=multipliers,
                context=context[:600],
            )
        )

    for m in EDGE_RE.finditer(text):
        add_edge(
            m.start(),
            m.end(),
            m.group("src").strip(),
            m.group("dst").strip(),
            re.sub(r"\s+", " ", m.group("src_detail").strip()),
            re.sub(r"\s+", " ", m.group("dst_detail").strip()),
        )

    for m in EDGE_NO_PAREN_RE.finditer(text):
        add_edge(m.start(), m.end(), m.group("src").strip(), m.group("dst").strip(), "", "")

    return edges


def _extract_threshold_candidates(text: str) -> list[str]:
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


def _extract_bullets(text: str, max_items: int = 50) -> list[str]:
    bullets: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("•") or s.startswith("-"):
            bullets.append(s[:200])
            if len(bullets) >= max_items:
                break
    return bullets


def main() -> int:
    if not CORE_BLOCKS_PATH.exists():
        raise SystemExit(f"Missing: {CORE_BLOCKS_PATH}")

    blocks_out: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []

    for rec in _read_jsonl(CORE_BLOCKS_PATH):
        block_id = str(rec.get("id") or "")
        major = str(rec.get("major") or "")
        num = rec.get("num")
        title = str(rec.get("title") or "")

        raw_text = str(rec.get("text") or "")
        norm_text = _fix_vertical_cjk(raw_text)

        roles = _extract_roles(norm_text)
        edges = _extract_edges(norm_text)
        thresholds = _extract_threshold_candidates(norm_text)
        bullets = _extract_bullets(norm_text)

        edges_out = [
            {
                "src": e.src,
                "dst": e.dst,
                "src_detail": e.src_detail,
                "dst_detail": e.dst_detail,
                "k": e.k,
                "multipliers": e.multipliers,
                "context": e.context,
            }
            for e in edges
        ]

        for eo in edges_out:
            all_edges.append({"block_id": block_id, "major": major, "num": num, "title": title, **eo})

        blocks_out.append(
            {
                "id": block_id,
                "major": major,
                "num": num,
                "title": title,
                "kind": rec.get("kind"),
                "start_line": rec.get("start_line"),
                "end_line": rec.get("end_line"),
                "roles": roles,
                "edges": edges_out,
                "threshold_candidates": thresholds,
                "bullet_candidates": bullets,
            }
        )

    out = {
        "source": str(CORE_BLOCKS_PATH),
        "blocks": blocks_out,
        "edges": all_edges,
        "stats": {
            "block_count": len(blocks_out),
            "edge_count": len(all_edges),
            "blocks_with_edges": sum(1 for b in blocks_out if b.get("edges")),
        },
        "notes": [
            "This is a raw extraction layer intended for iterative refinement.",
            "threshold_candidates and bullet_candidates are heuristic and not yet normalized.",
        ],
    }

    out_path = STEP3_DIR / "Data" / "step3_rules_raw.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    print(json.dumps(out["stats"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
