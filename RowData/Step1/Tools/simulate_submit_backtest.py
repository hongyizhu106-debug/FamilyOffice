from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simulate a web /submit and print singularity trace summary")
    p.add_argument("--n", type=int, default=3, help="Number of questions to answer (default: 3)")
    p.add_argument("--choice", type=str, default="A", help="Default choice key to use when available (default: A)")
    return p.parse_args()


def _latest_response_file(rubbish_dir: Path) -> Path | None:
    if not rubbish_dir.exists():
        return None
    files = sorted(rubbish_dir.glob("web_response_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def main() -> int:
    args = _parse_args()
    n = max(1, int(args.n))
    preferred = (args.choice or "").strip() or "A"

    from Step1.Constructor import Web_survey_app as ws

    bank = ws.load_bank()
    flat = list(ws.iter_questions_with_context(bank))
    picked = flat[:n]

    form_data: dict[str, str] = {}
    for q in picked:
        qid = q.get("id")
        if not isinstance(qid, str) or not qid:
            continue

        options = q.get("options") if isinstance(q.get("options"), list) else []
        keys = [o.get("key") for o in options if isinstance(o, dict) and isinstance(o.get("key"), str)]
        if not keys:
            continue

        choice = preferred if preferred in keys else keys[0]
        form_data[qid] = choice

    before = _latest_response_file(ws.RESPONSES_DIR)
    client = ws.app.test_client()
    resp = client.post("/submit", data=form_data)
    if resp.status_code >= 400:
        print(f"submit_http_status={resp.status_code}")
        return 2

    after = _latest_response_file(ws.RESPONSES_DIR)
    if after is None or after == before:
        print("ERROR: did not detect new response file")
        return 3

    payload = json.loads(after.read_text(encoding="utf-8"))
    sing = payload.get("singularity") if isinstance(payload, dict) else None

    print(f"saved={after}")
    print(f"answered_count={payload.get('answered_count')} total_count={payload.get('total_count')}")

    if isinstance(sing, dict) and sing.get("ok"):
        print(f"overall={sing.get('overall_score')} top={sing.get('top_categories')}")
        print(f"unmapped_codes={len(sing.get('unmapped_codes') or [])}")
        print(f"unassigned_categories={sing.get('unassigned_categories')}")

        trace = sing.get("trace") or []
        print(f"trace_items={len(trace)}")
        for item in trace[: min(5, len(trace))]:
            qid = item.get("question_id")
            choice = item.get("choice")
            codes = item.get("codes") or []
            mapped = [
                f"{c.get('code')}->{c.get('singularity') or 'UNMAPPED'}"
                for c in codes
                if isinstance(c, dict)
            ]
            print(f"- {qid} choice={choice} codes={mapped}")
    else:
        print(f"singularity_error={sing}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
