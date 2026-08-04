from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from Step1.Tools.planA_financial_analysis import generate_planA_analysis


@dataclass(frozen=True)
class Option:
    key: str
    label: str


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    options: tuple[Option, ...]


def _normalize_choice(raw: str) -> str:
    # Some shells/pipes may introduce BOM (\ufeff) or other invisible chars.
    return raw.replace("\ufeff", "").strip().upper()


def _prompt(prompt_text: str) -> str:
    try:
        return input(prompt_text)
    except (EOFError, KeyboardInterrupt):
        print("\n已退出。未保存本次作答。")
        raise SystemExit(130)


def _load_questions(path: Path) -> list[Question]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "questions" not in data:
        raise ValueError("Questions.json 格式错误：需要顶层对象并包含 questions 字段")

    raw_questions = data["questions"]
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("Questions.json 格式错误：questions 必须是非空数组")

    questions: list[Question] = []
    for idx, q in enumerate(raw_questions, start=1):
        if not isinstance(q, dict):
            raise ValueError(f"第 {idx} 题格式错误：必须为对象")
        qid = str(q.get("id") or idx)
        text = q.get("text")
        options = q.get("options")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"第 {idx} 题缺少 text")
        if not isinstance(options, list) or not options:
            raise ValueError(f"第 {idx} 题缺少 options")

        parsed_options: list[Option] = []
        seen_keys: set[str] = set()
        for opt in options:
            if not isinstance(opt, dict):
                raise ValueError(f"第 {idx} 题 options 格式错误")
            key = opt.get("key")
            label = opt.get("label")
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"第 {idx} 题存在空 key")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"第 {idx} 题存在空 label")
            key_norm = key.strip().upper()
            if key_norm in seen_keys:
                raise ValueError(f"第 {idx} 题选项 key 重复：{key_norm}")
            seen_keys.add(key_norm)
            parsed_options.append(Option(key=key_norm, label=label.strip()))

        questions.append(Question(id=qid, text=text.strip(), options=tuple(parsed_options)))

    return questions


def _print_header(title: str) -> None:
    line = "=" * max(10, len(title) * 2)
    print(line)
    print(title)
    print(line)


def _render_question(question: Question, number: int, total: int) -> None:
    print(f"\n[{number}/{total}] 第 {question.id} 题")
    print(question.text)
    for opt in question.options:
        print(f"  {opt.key}. {opt.label}")


def _ask_choice(question: Question) -> str:
    valid_keys = {opt.key for opt in question.options}
    keys_hint = "/".join(opt.key for opt in question.options)

    while True:
        raw = _prompt(f"请输入选项（{keys_hint}）：")
        choice = _normalize_choice(raw)
        if choice in valid_keys:
            return choice
        print(f"输入无效：{raw!r}。请仅输入 {keys_hint} 之一。")


def _option_label(question: Question, key: str) -> str:
    for opt in question.options:
        if opt.key == key:
            return opt.label
    return ""


def _choice_weight(choice: str, *, option_keys: Iterable[str]) -> float:
    """Map a chosen option to a fractional weight.

    Rule:
      - 4 options => A=0.25, B=0.50, C=0.75, D=1.00
      - 2 options => A=0.50, B=1.00
    Generalized: weight = (rank_index starting at 1) / option_count
    """

    keys = [str(k).strip().upper() for k in (option_keys or []) if str(k).strip()]
    if not keys:
        return 1.0
    c = (choice or "").strip().upper()
    try:
        idx = keys.index(c) + 1
    except ValueError:
        idx = 1
    if idx < 1:
        idx = 1
    if idx > len(keys):
        idx = len(keys)
    return round(idx / len(keys), 6)


def _ask_respondent_display() -> dict[str, str]:
    print("\n进入问卷前：请填写回答者称呼（用于报告展示）")
    surname = _prompt("姓氏（如：朱 / 欧阳）：").strip()
    surname = "".join(surname.split())
    if not surname:
        return {}

    honorific = _prompt("称谓（先生/女士，默认先生）：").strip()
    honorific = honorific or "先生"
    if honorific not in {"先生", "女士"}:
        honorific = "先生"

    return {
        "surname": surname,
        "honorific": honorific,
        "display": f"{surname}{honorific}",
    }


def _ask_listed_company(*, report_id_prefix: str) -> dict[str, Any]:
    print("\n可选：上市公司财务摘要（PlanA，支持 CN/US）")
    yn = _prompt("是否有上市公司？(Y/N，默认N)：").strip().upper()
    if yn not in {"Y", "YES", "1"}:
        return {}

    market = _prompt("市场（CN/US）：").strip().upper() or "CN"
    if market not in {"CN", "US"}:
        print("市场输入无效，已跳过上市公司摘要。")
        return {"error": "invalid market"}

    symbol = _prompt("代码（CN: 000001.SZ / US: NVDA）：").strip().upper()
    if not symbol:
        print("代码为空，已跳过上市公司摘要。")
        return {"error": "missing symbol"}

    period = _prompt("报告期YYYYMMDD（如20241231/20250930）：").strip()
    if not period or not period.isdigit() or len(period) != 8:
        print("报告期格式错误，已跳过上市公司摘要。")
        return {"error": "invalid period"}

    report_id = f"{report_id_prefix}-{market}-{symbol}"
    res = generate_planA_analysis(market=market, symbol=symbol, period=period, report_id=report_id)
    if not res.ok:
        print(f"上市公司摘要生成失败：{res.error}")
        return {"error": res.error, "market": market, "symbol": symbol, "period": period}

    print("\n上市公司财务摘要（PlanA）：")
    if res.analysis_text:
        print(res.analysis_text)
    return {
        "market": market,
        "symbol": symbol,
        "period": period,
        "analysis_text": res.analysis_text,
        "pdf_path": res.pdf_path,
        "html_path": res.html_path,
        "json_path": res.json_path,
    }


def run_survey(questions_path: Path, output_dir: Path) -> Path:
    questions = _load_questions(questions_path)
    _print_header("问卷作答控制台")
    print("说明：逐题输入选项字母（例如 A），输入错误会提示重输。")

    respondent = _ask_respondent_display()
    if respondent:
        respondent["listed_company_planA"] = _ask_listed_company(report_id_prefix=f"ROWSTEP1CLI-{respondent.get('display','')}".strip('-'))

    answers: list[dict[str, Any]] = []
    for i, q in enumerate(questions, start=1):
        _render_question(q, i, len(questions))
        key = _ask_choice(q)
        cw = _choice_weight(key, option_keys=[opt.key for opt in q.options])
        answers.append(
            {
                "question_id": q.id,
                "question_text": q.text,
                "choice": key,
                "choice_label": _option_label(q, key),
                "option_count": len(q.options),
                "choice_weight": cw,
            }
        )

    completed_at = datetime.now(timezone.utc)
    result = {
        "completed_at": completed_at.isoformat(),
        "questions_file": str(questions_path.name),
        "answers": answers,
    }

    if respondent:
        result["respondent"] = respondent

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"response_{completed_at.strftime('%Y%m%d_%H%M%S')}.json"
    out_path = output_dir / filename
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n已完成，作答已保存：")
    print(f"  {out_path}")
    return out_path


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    questions_path = root / "Data" / "Questions.json"
    output_dir = root / "Rubbish"

    if len(argv) >= 2:
        questions_path = Path(argv[1]).resolve()
    if len(argv) >= 3:
        output_dir = Path(argv[2]).resolve()

    if not questions_path.exists():
        print(f"找不到题库文件：{questions_path}")
        print("你可以先创建 Questions.json，或让我帮你从 Questions.pdf 抽取题目。")
        return 2

    run_survey(questions_path=questions_path, output_dir=output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
