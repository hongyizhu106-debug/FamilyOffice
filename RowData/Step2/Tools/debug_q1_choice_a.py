from __future__ import annotations

from pathlib import Path
import json
import sys

# Allow running as a standalone script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Step2.Constructor.singularity_engine import (
    compute_indicator_weights_from_answers,
    compute_singularity_stage_b_with_trace,
)


def main() -> None:
    bank_path = REPO_ROOT / "Step1" / "Data" / "Question_bank.json"
    mp_path = REPO_ROOT / "Step2" / "Data" / "indicator_singularity_map.json"

    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    first_q = bank["sections"][0]["groups"][0]["questions"][0]

    qid = first_q["id"]
    opt_keys = [str(o["key"]).strip().upper() for o in first_q["options"]]
    choice = "A"
    choice_weight = (opt_keys.index(choice) + 1) / len(opt_keys)

    codes = [str(m).split("（")[0].split("(")[0].strip() for m in first_q["mappings"]]

    answers = [
        {
            "question_id": qid,
            "question_number": first_q.get("number"),
            "choice": choice,
            "choice_weight": choice_weight,
            "option_count": len(opt_keys),
            "codes": codes,
        }
    ]

    stage_b = compute_singularity_stage_b_with_trace(answers=answers)

    mp = json.loads(mp_path.read_text(encoding="utf-8"))
    code_to_sing = mp["code_to_singularity"]
    totals = mp["singularity_indicator_totals"]

    cat = "权力/决策奇点"

    derived = compute_indicator_weights_from_answers(answers=answers)
    indicator_x = derived["indicator_weights"]

    hits = stage_b["category_hits"].get(cat)
    den = totals.get(cat)
    score = stage_b["category_scores"].get(cat)

    print("Q1:", qid)
    print("options:", opt_keys)
    print("choice:", choice)
    print("choice_weight:", choice_weight)
    print("codes:", codes)
    print("codes->category:", {c: code_to_sing.get(c) for c in codes})
    print("indicator_x:", indicator_x)
    print("category_hits[权力/决策奇点]=", hits)
    print("category_total_indicators=", den)
    print("category_score=", score)
    print("recompute=", round(100.0 * float(hits) / int(den), 1))


if __name__ == "__main__":
    main()

