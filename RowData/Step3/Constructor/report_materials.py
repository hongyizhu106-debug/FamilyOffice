from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from Step3.Constructor.relations_catalog import OUT_RELATIONS_PATH, ensure_relations_structured


@dataclass(frozen=True)
class Step3ReportMaterials:
    summary: dict[str, Any]
    resonance_risks: list[dict[str, Any]]
    conduction: dict[str, Any]
    plan: list[dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_relations() -> dict[str, Any]:
    ensure_relations_structured(OUT_RELATIONS_PATH)
    return _read_json(OUT_RELATIONS_PATH)


def _top_categories(stage_b: Any, max_n: int = 3) -> list[tuple[str, float]]:
    if not isinstance(stage_b, dict):
        return []
    top = stage_b.get("top_categories")
    if not isinstance(top, list):
        return []

    out: list[tuple[str, float]] = []
    for item in top[:max_n]:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        name = item[0]
        score = item[1]
        if not isinstance(name, str):
            continue
        try:
            v = float(score)
        except (TypeError, ValueError):
            v = 0.0
        out.append((name.replace("奇点", "").strip(), v))
    return out


def _category_score(stage_b: Any, category: str) -> float:
    if not isinstance(stage_b, dict):
        return 0.0
    scores = stage_b.get("category_scores")
    if not isinstance(scores, dict):
        return 0.0
    raw = scores.get(category if category.endswith("奇点") else f"{category}奇点")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _focus_layer_for_resonance(entry: dict[str, Any]) -> str:
    # Business-focused mapping: which defense layer should own the first action.
    layer = entry.get("layer")
    if layer == "第二层":
        return "根源层"
    if layer == "第一层":
        return "应急层/传导层"
    # Fallback based on involved types.
    types = entry.get("types")
    if isinstance(types, list) and any(t in {"认知/文化", "权力/决策", "时间"} for t in types if isinstance(t, str)):
        return "根源层"
    return "传导层"


def _priority_from_score(*, score: float, difficulty: str | None) -> str:
    bump = 0.0
    if difficulty == "极高":
        bump = 30.0
    elif difficulty == "高":
        bump = 15.0
    s = score + bump
    if s >= 160:
        return "P0"
    if s >= 120:
        return "P1"
    if s >= 80:
        return "P2"
    return "P3"


def _build_resonance_risks(stage_b: Any, relations: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    top = _top_categories(stage_b, max_n=3)
    top_names = {n for n, _ in top}

    # Prefer business-oriented resonance master if available.
    resonances = None
    if isinstance(relations, dict):
        rm = relations.get("resonance_master")
        if isinstance(rm, list) and rm:
            resonances = rm
        else:
            resonances = relations.get("resonances")
    if not isinstance(resonances, list):
        resonances = []

    scored: list[dict[str, Any]] = []
    for r in resonances:
        if not isinstance(r, dict):
            continue
        types = r.get("types")
        if not isinstance(types, list) or not types:
            continue

        # Business rule: at least one overlap with current top singularities.
        overlap = [t for t in types if isinstance(t, str) and t in top_names]
        if len(overlap) < 1:
            continue

        match_score = sum(_category_score(stage_b, t) for t in types if isinstance(t, str))
        difficulty = r.get("repair_difficulty") if isinstance(r.get("repair_difficulty"), str) else None
        priority = _priority_from_score(score=match_score, difficulty=difficulty)
        scored.append(
            {
                "name": r.get("name"),
                "types": types,
                "overlap": overlap,
                "match_score": round(match_score, 2),
                "priority": priority,
                "focus_layer": _focus_layer_for_resonance(r),
                "repair_difficulty": difficulty,
                "mechanism": r.get("mechanism"),
                "source": {"major": r.get("major"), "num": r.get("num"), "title": r.get("title")},
            }
        )

    scored.sort(key=lambda x: x.get("match_score", 0.0), reverse=True)
    return scored[:limit]


def _edge_strength(edge: dict[str, Any]) -> float:
    try:
        support = float(edge.get("support_count") or 0)
    except (TypeError, ValueError):
        support = 0.0
    mmax = edge.get("multiplier_max")
    try:
        mm = float(mmax) if mmax is not None else 1.0
    except (TypeError, ValueError):
        mm = 1.0
    return support * mm


def _build_conduction(stage_b: Any, relations: dict[str, Any]) -> dict[str, Any]:
    top = _top_categories(stage_b, max_n=3)
    if not top:
        return {"single_chain": [], "multi_chains": [], "resonance_amplification": [], "master_table": []}

    top_names = [n for n, _ in top]

    # 1) Business-grade master table (from core block 2.6) if available.
    master = relations.get("conduction_master") if isinstance(relations, dict) else None
    master_rows: list[dict[str, Any]] = []
    if isinstance(master, list) and master:
        for r in master:
            if not isinstance(r, dict):
                continue
            src = r.get("src")
            dst = r.get("dst")
            if isinstance(src, str) and src in top_names or isinstance(dst, str) and dst in top_names:
                master_rows.append(r)
        # Prefer rows with clearer governance node / M
        master_rows.sort(key=lambda x: (0 if x.get("m_value") is not None else 1, str(x.get("chain") or "")))

    # 2) Fallback/compat edge-based conduction (used by existing Step4 tables).
    edges = relations.get("edges") if isinstance(relations, dict) else None
    if not isinstance(edges, list):
        edges = []

    candidates = [e for e in edges if isinstance(e, dict) and e.get("src") in top_names]
    candidates.sort(key=_edge_strength, reverse=True)

    single: list[dict[str, Any]] = []
    if candidates:
        first = candidates[0]
        single.append(first)
        # Try a second hop.
        mid = first.get("dst")
        hop2 = [e for e in edges if isinstance(e, dict) and e.get("src") == mid]
        hop2.sort(key=_edge_strength, reverse=True)
        if hop2:
            single.append(hop2[0])

    multi = candidates[:5]
    amp = [e for e in candidates if (e.get("multiplier_max") or 0) and (e.get("multiplier_max") or 0) > 1.0]
    amp = amp[:5]

    return {
        "single_chain": single,
        "multi_chains": multi,
        "resonance_amplification": amp,
        "master_table": master_rows[:12],
    }


def _build_conduction_summary(stage_b: Any, conduction: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(conduction, dict):
        return {"text": "—"}
    multi = conduction.get("multi_chains")
    if not isinstance(multi, list):
        multi = []
    amp = conduction.get("resonance_amplification")
    if not isinstance(amp, list):
        amp = []

    master = conduction.get("master_table")
    if not isinstance(master, list):
        master = []

    total = len(multi)
    amp_cnt = len(amp)
    master_cnt = len(master)

    top = _top_categories(stage_b, max_n=3)
    top_chain = " × ".join([n for n, _ in top]) if top else "—"
    text = f"核心链路候选{total}条；其中放大链{amp_cnt}条；核心传导总表命中{master_cnt}条；核心奇点={top_chain}"
    return {
        "text": text,
        "candidate_count": total,
        "amplifier_count": amp_cnt,
        "master_table_count": master_cnt,
        "top_chain": top_chain,
    }


def _build_plan(resonance_risks: list[dict[str, Any]], conduction: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []

    for r in (resonance_risks or [])[:5]:
        if not isinstance(r, dict):
            continue
        plan.append(
            {
                "priority": r.get("priority"),
                "focus_layer": r.get("focus_layer"),
                "title": f"压制共振：{(r.get('types') or []) if isinstance(r.get('types'), list) else []}",
                "action": "优先建立应急授权/沟通与规则临时机制；同步配置传导阻断节点，避免风险在网络中放大。",
                "evidence": r.get("name"),
                "difficulty": r.get("repair_difficulty"),
            }
        )

    multi = conduction.get("multi_chains") if isinstance(conduction, dict) else []
    if isinstance(multi, list):
        for e in multi[:3]:
            if not isinstance(e, dict):
                continue
            plan.append(
                {
                    "priority": "P1" if (e.get("multiplier_max") or 0) > 1.0 else "P2",
                    "focus_layer": "传导层",
                    "title": f"设置治理节点：{e.get('src')}→{e.get('dst')}",
                    "action": "在关键链路上设置治理节点与预警阈值，明确责任人与处置SOP，降低传导系数K与放大系数A。",
                    "evidence": e.get("example_context"),
                    "difficulty": None,
                }
            )

    # If we have the business master table, turn governance nodes into concrete actions.
    master = conduction.get("master_table") if isinstance(conduction, dict) else []
    if isinstance(master, list):
        for r in master[:5]:
            if not isinstance(r, dict):
                continue
            chain = r.get("chain")
            gov = r.get("governance_node")
            trig = r.get("trigger")
            m = r.get("m")
            if chain and gov:
                plan.append(
                    {
                        "priority": "P1",
                        "focus_layer": "传导层",
                        "title": f"治理节点落地：{chain}",
                        "action": f"以“{gov}”作为关键治理节点，设定触发条件与应急授权机制；目标是降低K并通过调解系数M稳定传导。",
                        "evidence": f"触发={trig or '—'}；M={m or '—'}",
                        "difficulty": None,
                    }
                )

    return plan


def build_step3_report_materials(*, stage_b: Any) -> dict[str, Any]:
    """Build Step4-ready materials.

    Step4 should only *render* these materials; the modeling/assembly stays in Step3.
    """

    relations = _load_relations()
    resonance_risks = _build_resonance_risks(stage_b, relations)
    conduction = _build_conduction(stage_b, relations)
    summary = {
        "conduction": _build_conduction_summary(stage_b, conduction),
    }
    plan = _build_plan(resonance_risks, conduction)

    return Step3ReportMaterials(summary=summary, resonance_risks=resonance_risks, conduction=conduction, plan=plan).__dict__
