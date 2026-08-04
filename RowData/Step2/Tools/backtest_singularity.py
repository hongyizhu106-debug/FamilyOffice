from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# Ensure repo root is importable when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backtest singularity computation on an existing web_response_*.json")
    p.add_argument("response", type=Path, help="Path to Step1/Rubbish/web_response_*.json")
    p.add_argument("--out", type=Path, default=None, help="Optional output path for updated JSON")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    resp_path: Path = args.response
    if not resp_path.exists():
        raise SystemExit(f"Missing response: {resp_path}")

    resp = _load_json(resp_path)
    if not isinstance(resp, dict):
        raise SystemExit("Invalid response format")

    answers = resp.get("answers")
    code_weights = resp.get("code_weights")
    if not isinstance(answers, list) or not isinstance(code_weights, dict):
        raise SystemExit("Response missing answers/code_weights")

    from Step2.Constructor.singularity_engine import (
        compute_singularity_stage_b_with_trace,
        compute_singularity_with_trace,
    )

    sing = compute_singularity_with_trace(answers=answers, code_weights=code_weights)
    sing_b = compute_singularity_stage_b_with_trace(answers=answers)

    print(f"response={resp_path}")
    if sing.get("ok"):
        print(f"overall={sing.get('overall_score')}")
        print(f"top={sing.get('top_categories')}")
        print(f"unmapped_codes={len(sing.get('unmapped_codes') or [])}")
        print(f"unassigned_categories={sing.get('unassigned_categories')}")
        trace = sing.get("trace") or []
        print(f"trace_items={len(trace)}")
    else:
        print(f"ERROR: {sing.get('error')}")

    if sing_b.get("ok"):
        print(f"stage_b_overall={sing_b.get('overall_score')}")
        print(f"stage_b_top={sing_b.get('top_categories')}")
    else:
        print(f"stage_b_ERROR: {sing_b.get('error')}")

    if args.out is not None:
        out_path: Path = args.out
        resp["singularity_stage_a"] = sing
        resp["singularity_stage_b"] = sing_b
        resp["singularity"] = sing
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote={out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
