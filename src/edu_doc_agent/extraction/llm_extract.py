"""LLM-извлечение смысловых полей РПД (ADR-0002, часть 2) через шлюз `llm/`.

Для каждой задачи берётся текст нужного раздела, модель отвечает JSON по схеме, ответ
проверяется: невалидный JSON повторно запрашивается (до `MAX_RETRIES` раз), элементы с цитатой,
которой нет в тексте раздела, отбрасываются с предупреждением. Все вызовы идут через `LLMClient`,
конкретный провайдер сюда не протекает.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from edu_doc_agent.extraction import llm_prompts as prompts
from edu_doc_agent.extraction.llm_schemas import (
    ActiveFormsOutput,
    GradingRulesOutput,
    LLMActiveForm,
    LLMExtraction,
    LLMGradingRule,
    LLMPrerequisite,
    PrerequisitesOutput,
)
from edu_doc_agent.extraction.md_utils import MdSection, clean_text, split_sections
from edu_doc_agent.extraction.models import SourceRef
from edu_doc_agent.llm import LLMClient

MAX_RETRIES = 2  # повторов после первого ответа, как в ADR-0002


@dataclass(frozen=True)
class LLMTask:
    name: str
    prompt: str
    output: type[BaseModel]
    in_section: Callable[[MdSection], bool]


def _number(section: MdSection) -> str:
    return section.number or ""


TASKS = [
    LLMTask(
        "prerequisites",
        prompts.PREREQUISITES,
        PrerequisitesOutput,
        lambda s: _number(s) == "1.2",
    ),
    LLMTask(
        "active_forms",
        prompts.ACTIVE_FORMS,
        ActiveFormsOutput,
        lambda s: _number(s) == "1.4" and "активн" in s.heading.lower(),
    ),
    LLMTask(
        "grading_rules",
        prompts.GRADING_RULES,
        GradingRulesOutput,
        lambda s: _number(s).startswith("3.1.3"),
    ),
]
TASKS_BY_NAME = {t.name: t for t in TASKS}

_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—−"})


def normalize(text: str) -> str:
    """Для сравнения цитат и названий: без регистра, ё/е, тире и пробелов."""
    text = clean_text(text).translate(_DASHES).casefold().replace("ё", "е")
    return " ".join(text.split())


def quote_in_text(quote: str, text: str) -> bool:
    return bool(quote.strip()) and normalize(quote) in normalize(text)


def run_task(task: LLMTask, text: str, client: LLMClient) -> tuple[BaseModel | None, str | None]:
    """Один запрос с повторами. Возвращает (ответ, None) или (None, причина отказа)."""
    user = task.prompt.replace("{text}", text)
    schema = task.output.model_json_schema()
    error = ""
    for _ in range(MAX_RETRIES + 1):
        raw = client.complete_json(
            system=prompts.SYSTEM,
            user=user + prompts.REPAIR.format(error=error) if error else user,
            schema=schema,
        )
        try:
            return task.output.model_validate_json(raw), None
        except ValidationError as exc:
            error = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return None, f"{task.name}: ответ не прошёл проверку после {MAX_RETRIES + 1} попыток ({error})"


def _verified(items: list, text: str, task: str, warnings: list[str]) -> list:
    kept = []
    for item in items:
        if quote_in_text(item.quote, text):
            kept.append(item)
        else:
            warnings.append(
                f"{task}: цитата не найдена в тексте раздела, элемент отброшен: {item.quote[:60]!r}"
            )
    return kept


def extract_with_llm(
    md: str, file: str, client: LLMClient, tasks: list[str] | None = None
) -> LLMExtraction:
    """Прогоняет выбранные задачи (по умолчанию все) по разделам md-документа."""
    result = LLMExtraction(file=file)
    sections = split_sections(md)
    for task in (TASKS_BY_NAME[n] for n in tasks) if tasks else TASKS:
        for section in (s for s in sections if task.in_section(s)):
            text = "\n".join(ln for ln in section.text.split("\n") if ln.strip())
            if not text:
                continue
            ref = SourceRef(file=file, section=section.heading, line=section.line)
            output, problem = run_task(task, text, client)
            if output is None:
                result.warnings.append(f"{problem} [{section.heading[:40]}]")
                continue
            _collect(task.name, output, text, ref, result)
    return result


def _collect(
    name: str, output: BaseModel, text: str, ref: SourceRef, result: LLMExtraction
) -> None:
    if isinstance(output, PrerequisitesOutput):
        for item in _verified(output.items, text, name, result.warnings):
            result.prerequisites.append(LLMPrerequisite(**item.model_dump(), source=ref))
    elif isinstance(output, ActiveFormsOutput):
        if output.total_hours is not None and re.search(
            rf"\b{output.total_hours:g}\b", text.replace(",", ".")
        ):
            result.active_total_hours = output.total_hours
        elif output.total_hours is not None:
            result.warnings.append(
                f"{name}: общий объём {output.total_hours:g} ч не найден в тексте"
            )
        for item in _verified(output.items, text, name, result.warnings):
            result.active_forms.append(LLMActiveForm(**item.model_dump(), source=ref))
    elif isinstance(output, GradingRulesOutput):
        for item in _verified(output.rules, text, name, result.warnings):
            result.grading_rules.append(LLMGradingRule(**item.model_dump(), source=ref))
