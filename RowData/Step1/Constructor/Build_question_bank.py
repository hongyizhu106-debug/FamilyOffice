from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MODULE_RE = re.compile(r"^[一二三四五六七八九十]+、\s*")
# PDF 抽取文本里常出现 "问题组 10：" 这种空格，需兼容空白
GROUP_RE = re.compile(r"^问题组\s*\d+\s*[:：]")
QUESTION_START_RE = re.compile(r"^(\d+)[\.、]")
OPTION_RE = re.compile(r"^([A-Z])[\.、]\s*(.*)$")
MAPPING_RE = re.compile(r"^M\d+[-－]")
MAPPING_ITEM_RE = re.compile(r"^\s*(?P<code>[^（(]+?)\s*[（(](?P<name>[^）)]+)[）)]\s*$")

# Heuristics for semantic option ordering (low risk -> high risk).
NEGATIVE_CONTEXT_RE = re.compile(
    r"是否因|是否出现|是否发生|是否导致|是否影响|是否延误|是否流失|是否冲突|是否争议|"
    r"是否失真|是否偏差|是否失误|是否脱节|是否滞后|是否依赖|是否中断|风险|问题|危机|泄露"
)
POSITIVE_CONTEXT_RE = re.compile(
    r"是否有|是否具备|是否存在|是否清楚|是否参与|是否使用|是否支持|是否认可|是否纳入|"
    r"是否更新|是否能够|是否定期|是否建立|是否形成|是否提供|是否设置|是否配备|是否有机制|"
    r"是否有预案|是否有计划|是否有文件|是否有制度|是否有流程|是否有明确|是否有足够"
)

POSITIVE_SCALE = [
    re.compile(r"有且|非常|高度|完全|全面|充分|清晰|完善|有效|系统化|定期|每年|严格|快速|强大|充足|严格执行|积极"),
    re.compile(r"基本|大致|尚可|一般|较|偶尔|有但|略有|部分|基本具备|基本覆盖|基本畅通"),
    re.compile(r"不够|不足|滞后|有限|较少|很少|不完善|效果一般|有所担忧|存在未解决"),
    re.compile(r"没有|不明确|不需要|不支持|不认可|明显不|从未|未|形同虚设|孤立无援"),
]

NEGATIVE_SCALE = [
    re.compile(r"从未|完全没有|没有|无任何|无影响|未发生|未出现"),
    re.compile(r"极少|很少|少量|偶尔|略有|轻微|不大|基本无"),
    re.compile(r"有时|有所|部分|中度|一般|有一定"),
    re.compile(r"经常|明显|较多|多次|较大|较高|中高"),
    re.compile(r"总是|严重|非常严重|极度|极高|彻底|完全|形同虚设|孤立无援|不清楚|不知道"),
]


def _clean_line(line: str) -> str:
    return line.replace("\ufeff", "").strip()


def _join_fragments(fragments: list[str]) -> str:
    # Joining without spaces is important because PDF extraction breaks Chinese words mid-line.
    text = "".join(s.strip() for s in fragments if s.strip())
    # Normalize repeated whitespace that may appear inside extracted spans.
    return re.sub(r"\s+", " ", text).strip()


def _infer_context(question_text: str) -> str:
    if NEGATIVE_CONTEXT_RE.search(question_text or ""):
        return "negative"
    if POSITIVE_CONTEXT_RE.search(question_text or ""):
        return "positive"
    return "neutral"


def _semantic_rank(label: str, *, context: str) -> int | None:
    text = label or ""
    scale = NEGATIVE_SCALE if context == "negative" else POSITIVE_SCALE
    rank: int | None = None
    for idx, pattern in enumerate(scale):
        if pattern.search(text):
            rank = idx if rank is None else max(rank, idx)
    return rank


def _relabel_option_keys(options: list[Option]) -> None:
    for idx, opt in enumerate(options):
        if 0 <= idx < 26:
            opt.key = chr(ord("A") + idx)


def _reorder_options_by_semantics(question: Question) -> bool:
    if not question.options:
        return False

    context_hint = _infer_context(question.text)
    contexts = [context_hint] if context_hint != "neutral" else ["negative", "positive"]

    best_ranks: list[int] | None = None
    best_coverage = -1
    for ctx in contexts:
        ranks = [_semantic_rank(opt.label, context=ctx) for opt in question.options]
        coverage = sum(1 for r in ranks if r is not None)
        if coverage > best_coverage:
            best_coverage = coverage
            best_ranks = ranks

    if best_ranks is None or best_coverage < len(question.options):
        return False

    indexed = list(enumerate(question.options))
    indexed.sort(key=lambda pair: (best_ranks[pair[0]], pair[0]))
    new_options = [opt for _, opt in indexed]

    if [opt.label for opt in new_options] == [opt.label for opt in question.options]:
        return False

    question.options = new_options
    _relabel_option_keys(question.options)
    return True


@dataclass
class Option:
    key: str
    label: str


@dataclass
class Question:
    id: str
    number: str
    text: str
    options: list[Option] = field(default_factory=list)
    mappings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "text": self.text,
            "options": [
                {"key": opt.key, "label": opt.label}
                for opt in self.options
            ],
            "mappings": self.mappings,
        }


@dataclass
class Group:
    title: str
    questions: list[Question] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "questions": [q.to_dict() for q in self.questions],
        }


@dataclass
class Section:
    title: str
    groups: list[Group] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "groups": [g.to_dict() for g in self.groups],
        }


@dataclass
class Bank:
    title: str
    sections: list[Section] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "sections": [s.to_dict() for s in self.sections],
        }


@dataclass
class BankBuilder:
    sections: list[Section] = field(default_factory=list)
    current_section: Section | None = None
    current_group: Group | None = None

    def ensure_section(self, default_title: str) -> Section:
        if self.current_section is None:
            self.current_section = Section(title=default_title)
            self.sections.append(self.current_section)
        return self.current_section

    def ensure_group(self, default_title: str) -> Group:
        section = self.ensure_section("未分模块")
        if self.current_group is None:
            self.current_group = Group(title=default_title)
            section.groups.append(self.current_group)
        return self.current_group

    def start_section(self, title: str) -> None:
        self.current_section = Section(title=title)
        self.sections.append(self.current_section)
        self.current_group = None

    def start_group(self, title: str) -> None:
        section = self.ensure_section("未分模块")
        self.current_group = Group(title=title)
        section.groups.append(self.current_group)

    def add_question(self, question: Question) -> None:
        group = self.ensure_group("未分问题组")
        group.questions.append(question)


def parse_extracted_text(lines: list[str]) -> dict[str, Any]:
    # Output schema:
    # {
    #   title: str,
    #   sections: [
    #     { title: str, groups: [ { title: str, questions: [...] } ] }
    #   ]
    # }

    title = ""
    builder = BankBuilder()

    i = 0
    n = len(lines)

    # Pre-clean lines
    cleaned: list[str] = []
    for raw in lines:
        s = _clean_line(raw)
        if not s:
            continue
        # Drop repeated table headers
        if s in {"问题", "选项设计", "映射指标"}:
            continue
        cleaned.append(s)

    lines = cleaned
    n = len(lines)

    if n:
        # First non-empty line is usually the document title.
        title = lines[0]

    while i < n:
        line = lines[i]

        if MODULE_RE.match(line):
            builder.start_section(line)
            i += 1
            continue

        if GROUP_RE.match(line):
            builder.start_group(line)
            i += 1
            continue

        q_match = QUESTION_START_RE.match(line)
        if q_match:
            builder.ensure_group("未分问题组")

            q_number = q_match.group(1)
            try:
                q_number_int = int(q_number)
            except ValueError:
                q_number_int = None
            # Collect question text fragments until first option.
            text_frags: list[str] = [line[q_match.end() :].strip()]
            i += 1

            # Gather text continuation
            while i < n:
                peek = lines[i]
                if OPTION_RE.match(peek) or QUESTION_START_RE.match(peek) or GROUP_RE.match(peek) or MODULE_RE.match(peek):
                    break
                # Some mappings may appear without options in weird layouts; treat them later.
                if MAPPING_RE.match(peek):
                    break
                text_frags.append(peek)
                i += 1

            question = Question(
                id="",
                number=q_number,
                text=_join_fragments(text_frags),
            )

            # Gather options
            while i < n:
                peek = lines[i]
                opt_match = OPTION_RE.match(peek)
                if not opt_match:
                    break

                key = opt_match.group(1)
                label_frags = [opt_match.group(2)]
                i += 1

                # Option label can wrap; keep consuming until next option/question/header/mapping.
                while i < n:
                    cont = lines[i]
                    if OPTION_RE.match(cont) or QUESTION_START_RE.match(cont) or GROUP_RE.match(cont) or MODULE_RE.match(cont) or MAPPING_RE.match(cont):
                        break
                    label_frags.append(cont)
                    i += 1

                question.options.append(Option(key=key, label=_join_fragments(label_frags)))

            _reorder_options_by_semantics(question)

            # Gather mapping indicator lines
            while i < n:
                peek = lines[i]
                if QUESTION_START_RE.match(peek) or GROUP_RE.match(peek) or MODULE_RE.match(peek):
                    break
                if MAPPING_RE.match(peek):
                    question.mappings.append(peek)
                i += 1

            if q_number_int is None or q_number_int <= 5:
                current_group = builder.ensure_group("未分问题组")
                question.id = f"{current_group.title}#{question.number}"
                builder.add_question(question)
            continue

        i += 1

    # If title line is also a module header, keep it; otherwise store separately.
    bank = Bank(title=title or "问卷", sections=builder.sections)
    return bank.to_dict()


def normalize_mappings(bank: dict[str, Any]) -> int:
    """Normalize mapping codes for duplicate indicator names.

    Rule: for the same indicator name (text inside parentheses), keep the code
    from the first time this name appears.

    Returns number of mapping items modified.
    """

    name_to_first_code: dict[str, str] = {}
    changed = 0

    for section in bank.get("sections", []):
        for group in section.get("groups", []):
            for q in group.get("questions", []):
                mappings = q.get("mappings")
                if not isinstance(mappings, list):
                    continue

                new_list: list[str] = []
                modified = False

                for item in mappings:
                    if not isinstance(item, str):
                        new_list.append(item)
                        continue

                    m = MAPPING_ITEM_RE.match(item)
                    if not m:
                        new_list.append(item)
                        continue

                    code = m.group("code").strip()
                    name = m.group("name").strip()

                    if name not in name_to_first_code:
                        name_to_first_code[name] = code
                        new_list.append(f"{code}（{name}）")
                        continue

                    first_code = name_to_first_code[name]
                    if code != first_code:
                        new_list.append(f"{first_code}（{name}）")
                        changed += 1
                        modified = True
                    else:
                        new_list.append(f"{code}（{name}）")

                if modified:
                    q["mappings"] = new_list

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Build question bank JSON from extracted PDF text.")
    parser.add_argument(
        "--in",
        dest="in_path",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "Data" / "Questions_extracted.txt",
        help="Input extracted text file (default: Data/Questions_extracted.txt)",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "Data" / "Question_bank.json",
        help="Output JSON path (default: Data/Question_bank.json)",
    )
    args = parser.parse_args()

    lines = args.in_path.read_text(encoding="utf-8").splitlines()
    bank = parse_extracted_text(lines)

    changed = normalize_mappings(bank)
    if changed:
        print(f"Normalized mappings: changed {changed} item(s)")

    args.out_path.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote question bank: {args.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
