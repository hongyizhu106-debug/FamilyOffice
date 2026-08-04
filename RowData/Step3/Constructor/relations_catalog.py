from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
DATA_DIR = STEP3_DIR / "Data"

CORE_BLOCKS_PATH = DATA_DIR / "step3_core_blocks.jsonl"
RULES_RAW_PATH = DATA_DIR / "step3_rules_raw.json"
OUT_RELATIONS_PATH = DATA_DIR / "step3_relations_structured.json"


_HEADER_TOKENS = {
    "共振组合",
    "传导机制",
    "归因分析",
    "最终后果",
    "修复",
    "难度",
    "修复难度",
    "共振强度",
}


_DIFFICULTY_TOKENS = {"极高", "高", "中", "低"}

_CONDUCTION_HEADER_TOKENS = {
    "传导链路",
    "奇点类型",
    "传导模式",
    "传导系数(K)",
    "临界/触发条件",
    "起点归因角色",
    "终点归因角色",
    "治理节点",
    "调解系数(M)",
}

_SINGULARITY_ATTR_TOKENS = {"根源性", "衍生性", "诱发性"}
_MODE_TOKENS = {"线性", "非线性", "突变"}


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _extract_resonance_table_compact(text: str) -> list[dict[str, Any]]:
    """Extract resonance combos from compacted text.

    Intended for table-like sections such as "同层致命共振" where OCR often breaks lines.
    We focus on: combo (A+B共振), layer marker (第一层/第二层), and repair difficulty.
    """

    c = _compact(text)
    if not c:
        return []

    combo_re = re.compile(r"(?P<a>[\u4e00-\u9fff/]+)\+(?P<b>[\u4e00-\u9fff/]+)共振")
    matches = list(combo_re.finditer(c))
    if not matches:
        return []

    out: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        seg_start = m.start()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(c)
        seg = c[seg_start:seg_end]

        a = _normalize_singularity_type(m.group("a") or "")
        b = _normalize_singularity_type(m.group("b") or "")
        types = [_normalize_category_name(a), _normalize_category_name(b)]
        types = [t for t in types if t]

        # Determine layer by nearest marker within a small window before combo.
        pre = c[max(0, seg_start - 120) : seg_start]
        layer = None
        if "第一层共振" in pre:
            layer = "第一层"
        elif "第二层共振" in pre:
            layer = "第二层"

        # Difficulty tends to appear near end of a row; pick the last token seen.
        difficulty = None
        for tok in ("极高", "高", "中", "低"):
            if tok in seg:
                difficulty = tok
        if difficulty not in _DIFFICULTY_TOKENS:
            difficulty = None

        out.append(
            {
                "name": f"{a}+{b}共振",
                "types": types,
                "layer": layer,
                "repair_difficulty": difficulty,
            }
        )

    # De-dup by (name, layer)
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for r in out:
        k = f"{r.get('name')}|{r.get('layer') or ''}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            yield json.loads(s)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _normalize_singularity_type(name: str) -> str:
    n = (name or "").strip()
    if n in {"决策", "权力"}:
        return "权力/决策"
    if n in {"认知", "文化"}:
        return "认知/文化"
    return n


def _normalize_category_name(cat: str) -> str:
    c = (cat or "").strip()
    if c.endswith("奇点"):
        c = c[: -len("奇点")]
    c = c.strip()
    return _normalize_singularity_type(c)


def _parse_combo_part(part: str) -> dict[str, str]:
    """Parse a single term like '人物奇点（失控/失信）' or '时间' """

    s = (part or "").strip()
    s = re.sub(r"\s+", "", s)

    # Try with parentheses.
    m = re.match(r"(?P<typ>[\u4e00-\u9fff/]+)(?:奇点)?(?:（(?P<detail>[^）]{0,80})）)?$", s)
    if m:
        return {
            "type": _normalize_singularity_type(m.group("typ") or ""),
            "detail": (m.group("detail") or "").strip(),
        }

    # Fallback: raw.
    return {"type": _normalize_singularity_type(s.replace("奇点", "")), "detail": ""}


def _extract_resonances_from_block(block_text: str) -> list[dict[str, Any]]:
    """Heuristic extraction of resonance combos from a single core block."""

    lines = [ln.strip() for ln in (block_text or "").splitlines() if ln.strip()]
    if not lines:
        return []

    resonances: list[dict[str, Any]] = []
    current_name: str | None = None
    current_combo: list[dict[str, str]] = []
    buf_mech: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_combo, buf_mech
        if current_name and current_combo:
            types = [c.get("type", "") for c in current_combo if c.get("type")]
            resonances.append(
                {
                    "name": current_name,
                    "components": current_combo,
                    "types": types,
                    "mechanism": " ".join(buf_mech).strip() or None,
                }
            )
        current_name = None
        current_combo = []
        buf_mech = []

    for raw in lines:
        s = raw
        if s in _HEADER_TOKENS:
            continue

        # A row name often ends with "共振".
        if s.endswith("共振") and len(s) <= 18 and "高危" not in s and "致命" not in s:
            # New resonance row.
            flush()
            current_name = s
            continue

        # Combo line with explicit '奇点 + 奇点' form.
        if "+" in s or "＋" in s:
            # Exclude obvious non-combo lines.
            if "共振" in s and "奇点" not in s and len(s) <= 18:
                # e.g. 人物+时间共振 (OCR may split)
                parts = re.split(r"[+＋]", s.replace("共振", ""))
                parts = [p for p in parts if p]
                if len(parts) >= 2:
                    current_combo = [_parse_combo_part(p) for p in parts]
                continue

            parts = re.split(r"[+＋]", s)
            parts = [p for p in parts if p]
            parsed = [_parse_combo_part(p) for p in parts]
            parsed = [p for p in parsed if p.get("type")]
            if len(parsed) >= 2:
                current_combo = parsed
                continue

        # Otherwise treat as mechanism/narrative if we're inside a resonance row.
        if current_name:
            # Keep short context; avoid repeated headers.
            if len(s) <= 120 and s not in _HEADER_TOKENS:
                buf_mech.append(s)

    flush()
    return resonances


def _to_float_maybe(s: str) -> float | None:
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def _extract_conduction_master_from_block(text: str) -> list[dict[str, Any]]:
    """Parse the Step3 core block 2.6 table into business-usable rows.

    The upstream extraction often contains a mix of literal '\\n' markers and real newlines,
    plus mid-token line breaks like 'D-\nDet'. We normalize first, then parse rows.
    """

    if not text:
        return []

    t = str(text)

    # Normalize: literal "\\n" -> newline; normalize CRLF; join hyphen line breaks.
    t = t.replace("\\n", "\n")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"-\s*\n\s*", "-", t)

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        return []

    # Skip until after header.
    start_idx = 0
    for i, ln in enumerate(lines):
        if "调解系数" in ln:
            start_idx = i + 1
            break

    data = [ln for ln in lines[start_idx:] if ln not in _CONDUCTION_HEADER_TOKENS]
    if not data:
        return []

    def is_mode(x: str) -> bool:
        return any(tok in x for tok in _MODE_TOKENS)

    def is_attr(x: str) -> bool:
        return any(tok in x for tok in _SINGULARITY_ATTR_TOKENS)

    def is_roleish(x: str) -> bool:
        # e.g. D-Det, R-Init/D-Det, A-Lock, D-Det/C-Con, "R-Init ×"
        return bool(re.fullmatch(r"[A-Z]-[A-Za-z]+(?:/[A-Z]-[A-Za-z]+)?(?:\s*×\s*)?", x))

    rows: list[dict[str, Any]] = []
    i = 0
    while i < len(data):
        if data[i].startswith("注：") or data[i].startswith("注:"):
            break

        # 1) chain (may be split across lines)
        chain = data[i]
        i += 1
        while i < len(data) and not is_attr(data[i]):
            # If next token looks like a continuation (no attrs/mode), append.
            if data[i] in _CONDUCTION_HEADER_TOKENS:
                i += 1
                continue
            if any(tok in data[i] for tok in _SINGULARITY_ATTR_TOKENS):
                break
            # Avoid accidentally absorbing the mode row.
            if is_mode(data[i]):
                break
            chain += data[i]
            i += 1
            if "→" in chain and is_attr(data[i - 1] if i - 1 < len(data) else ""):
                break

        if i >= len(data) or not is_attr(data[i]):
            # Can't form a row.
            continue

        # 2) singularity attr
        attr = data[i]
        i += 1
        while i < len(data) and not is_mode(data[i]):
            # Sometimes this cell is broken across lines.
            if is_attr(data[i]) and "→" not in attr:
                attr += data[i]
                i += 1
                continue
            break

        if i >= len(data):
            break

        # 3) mode
        mode = data[i]
        i += 1

        # 4) K (can be multi-line)
        if i >= len(data):
            break
        k = data[i]
        i += 1
        while i < len(data) and (data[i].startswith("K") or "（R=" in data[i] or "(R=" in data[i]):
            k += " " + data[i]
            i += 1

        # 5) trigger/threshold (can be multi-line)
        if i >= len(data):
            break
        trigger = data[i]
        i += 1
        while i < len(data) and ("T=" in data[i] or "S=" in data[i] or "率" in data[i] or "年" in data[i]) and not is_roleish(data[i]):
            # Stop if it starts looking like a role code.
            if is_roleish(data[i]):
                break
            trigger += data[i]
            i += 1

        # 6) start role (may include resonance '×' and split into two tokens)
        if i >= len(data):
            break
        start_role = data[i]
        i += 1
        if start_role.endswith("×") and i < len(data) and is_roleish(data[i]):
            start_role = f"{start_role} {data[i]}"
            i += 1

        # 7) end role
        if i >= len(data):
            break
        end_role = data[i]
        i += 1
        if end_role.endswith("×") and i < len(data) and is_roleish(data[i]):
            end_role = f"{end_role} {data[i]}"
            i += 1

        # 8) governance node (consume until float-like M)
        if i >= len(data):
            break
        governance = data[i]
        i += 1
        while i < len(data) and _to_float_maybe(data[i]) is None:
            # Avoid swallowing the next chain by stopping on arrow if we already have a node.
            if "→" in data[i] and "节点" in governance:
                break
            governance += data[i]
            i += 1

        # 9) mediation M
        if i >= len(data):
            break
        m_raw = data[i]
        i += 1

        chain = chain.replace(" ", "")
        chain = chain.replace("—", "-")
        src = None
        dst = None
        if "→" in chain:
            parts = chain.split("→", 1)
            src = _normalize_singularity_type(parts[0])
            dst = _normalize_singularity_type(parts[1])

        rows.append(
            {
                "chain": chain,
                "src": src,
                "dst": dst,
                "singularity_types": attr,
                "mode": mode,
                "k": k,
                "trigger": trigger,
                "start_role": start_role,
                "end_role": end_role,
                "governance_node": governance,
                "m": m_raw,
                "m_value": _to_float_maybe(m_raw),
            }
        )

    return rows


def build_relations_structured_data() -> dict[str, Any]:
    if not CORE_BLOCKS_PATH.exists():
        raise FileNotFoundError(f"Missing: {CORE_BLOCKS_PATH}")

    rules_raw: dict[str, Any] | None = None
    if RULES_RAW_PATH.exists():
        rules_raw = _read_json(RULES_RAW_PATH)

    # 1) Transmission edges (from Step3 raw rules extraction)
    edge_items: list[dict[str, Any]] = []
    if isinstance(rules_raw, dict):
        edges = rules_raw.get("edges")
        if isinstance(edges, list):
            for e in edges:
                if not isinstance(e, dict):
                    continue
                src = _normalize_singularity_type(str(e.get("src") or "").replace("奇点", "").strip())
                dst = _normalize_singularity_type(str(e.get("dst") or "").replace("奇点", "").strip())
                if not src or not dst:
                    continue
                edge_items.append(
                    {
                        "src": src,
                        "dst": dst,
                        "src_detail": str(e.get("src_detail") or "").strip(),
                        "dst_detail": str(e.get("dst_detail") or "").strip(),
                        "k": e.get("k") if isinstance(e.get("k"), list) else [],
                        "multipliers": e.get("multipliers") if isinstance(e.get("multipliers"), list) else [],
                        "context": str(e.get("context") or "").strip(),
                        "major": str(e.get("major") or ""),
                        "num": e.get("num"),
                        "title": e.get("title"),
                        "block_id": e.get("block_id"),
                    }
                )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in edge_items:
        grouped[(e["src"], e["dst"])].append(e)

    edges_agg: list[dict[str, Any]] = []
    for (src, dst), items in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0][0], kv[0][1])):
        multipliers: list[float] = []
        k_tokens: list[str] = []
        example_context = None
        for it in items:
            for m in it.get("multipliers") or []:
                try:
                    multipliers.append(float(m))
                except (TypeError, ValueError):
                    pass
            for kk in it.get("k") or []:
                if isinstance(kk, str) and kk.strip() and kk.strip() not in k_tokens:
                    k_tokens.append(kk.strip())
            if not example_context:
                ctx = (it.get("context") or "").strip()
                if ctx:
                    example_context = ctx

        edges_agg.append(
            {
                "src": src,
                "dst": dst,
                "support_count": len(items),
                "k_examples": k_tokens[:6],
                "multiplier_max": max(multipliers) if multipliers else None,
                "multiplier_min": min(multipliers) if multipliers else None,
                "multiplier_avg": (sum(multipliers) / len(multipliers)) if multipliers else None,
                "example_context": example_context,
            }
        )

    # 2) Resonance combos (from Step3 core blocks)
    resonance_entries: list[dict[str, Any]] = []
    resonance_master: list[dict[str, Any]] = []
    conduction_master: list[dict[str, Any]] = []
    for rec in _read_jsonl(CORE_BLOCKS_PATH):
        title = str(rec.get("title") or "")
        num = str(rec.get("num") or "")
        if "共振" not in title:
            # Still allow extraction of the conduction master table.
            if num != "2.6" and "核心传导链路总表" not in title:
                continue
        txt = str(rec.get("text") or "")

        if num == "2.6" or "核心传导链路总表" in title:
            rows = _extract_conduction_master_from_block(txt)
            for r in rows:
                conduction_master.append(
                    {
                        "major": str(rec.get("major") or ""),
                        "num": num,
                        "title": title,
                        **r,
                    }
                )

        # Business-oriented extraction for table-like sections.
        if "致命共振" in title or "同层致命共振" in title:
            for r in _extract_resonance_table_compact(txt):
                resonance_master.append(
                    {
                        "major": str(rec.get("major") or ""),
                        "num": str(rec.get("num") or ""),
                        "title": title,
                        **r,
                    }
                )

        extracted = _extract_resonances_from_block(txt)
        for r in extracted:
            types = [_normalize_category_name(t) for t in (r.get("types") or [])]
            types = [t for t in types if t]
            resonance_entries.append(
                {
                    "major": str(rec.get("major") or ""),
                    "num": str(rec.get("num") or ""),
                    "title": title,
                    "name": r.get("name"),
                    "types": types,
                    "components": r.get("components"),
                    "mechanism": r.get("mechanism"),
                }
            )

    # De-dup resonance entries by (name, types)
    seen_res: set[str] = set()
    uniq_res: list[dict[str, Any]] = []
    for r in resonance_entries:
        key = f"{r.get('name')}|{','.join(r.get('types') or [])}"
        if key in seen_res:
            continue
        seen_res.add(key)
        uniq_res.append(r)

    # De-dup resonance master by (name, types)
    seen_rm: set[str] = set()
    uniq_rm: list[dict[str, Any]] = []
    for r in resonance_master:
        types = r.get("types")
        if not isinstance(types, list):
            types = []
        key = f"{r.get('name')}|{','.join([t for t in types if isinstance(t, str)])}"
        if key in seen_rm:
            continue
        seen_rm.add(key)
        uniq_rm.append(r)

    return {
        "source": {
            "core_blocks": str(CORE_BLOCKS_PATH),
            "rules_raw": str(RULES_RAW_PATH),
        },
        "edges": edges_agg,
        "resonances": uniq_res,
        "resonance_master": uniq_rm,
        "conduction_master": conduction_master,
        "stats": {
            "edge_pairs": len(edges_agg),
            "resonance_count": len(uniq_res),
            "resonance_master_count": len(uniq_rm),
            "conduction_master_count": len(conduction_master),
        },
    }


def ensure_relations_structured(path: Path = OUT_RELATIONS_PATH) -> Path:
    """Ensure Step3 relations structured json exists; build if missing."""

    def src_mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    if path.exists():
        # If schema evolved, rebuild even if mtimes look fresh.
        try:
            existing = _read_json(path)
            if not isinstance(existing, dict) or "conduction_master" not in existing:
                raise ValueError("missing conduction_master")
        except Exception:
            existing = None

        out_m = src_mtime(path)
        src_m = max(src_mtime(CORE_BLOCKS_PATH), src_mtime(RULES_RAW_PATH))
        if existing is not None and out_m >= src_m:
            return path

    data = build_relations_structured_data()
    _write_json(path, data)
    return path


def write_relations_structured(path: Path = OUT_RELATIONS_PATH) -> Path:
    data = build_relations_structured_data()
    _write_json(path, data)
    return path
