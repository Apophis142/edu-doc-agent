"""Прогон LLM-извлечения по документу: схема, повторы, проверка цитат, источники."""

import json
from pathlib import Path

from edu_doc_agent.extraction.llm_extract import MAX_RETRIES, extract_with_llm
from edu_doc_agent.llm import FakeLLMClient, LLMCall

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rpd_full_synthetic.md"
MD = FIXTURE.read_text(encoding="utf-8")

PREREQ = {
    "items": [
        {
            "name": "алгебра и геометрия",
            "kind": "дисциплина",
            "relation": "предшествует",
            "quote": "«Алгебра и геометрия»",
        }
    ]
}
ACTIVE = {
    "total_hours": None,
    "items": [
        {
            "kind": "консультации",
            "hours": 2,
            "mandatory": True,
            "quote": "Консультации в активной форме – 2 часа",
        }
    ],
}
RULES = {"rules": []}


def _by_prompt(call: LLMCall) -> str:
    if "пререквизиты" in call.user:
        return json.dumps(PREREQ, ensure_ascii=False)
    if "активных и интерактивных" in call.user:
        return json.dumps(ACTIVE, ensure_ascii=False)
    return json.dumps(RULES)


def test_all_tasks_run_and_items_get_sources() -> None:
    client = FakeLLMClient(respond=_by_prompt)
    result = extract_with_llm(MD, "rpd.md", client)
    assert [p.name for p in result.prerequisites] == ["алгебра и геометрия"]
    assert result.prerequisites[0].source.section.startswith("1.2.")
    assert result.prerequisites[0].source.line is not None
    assert [(f.kind, f.hours) for f in result.active_forms] == [("консультации", 2)]
    assert result.warnings == []
    assert len(client.calls) == 3  # по одному вызову на задачу: 1.2, 1.4, 3.1.3


def test_each_call_has_schema_and_section_text_only() -> None:
    client = FakeLLMClient(respond=_by_prompt)
    extract_with_llm(MD, "rpd.md", client, tasks=["prerequisites"])
    (call,) = client.calls
    assert "items" in call.schema["properties"]
    assert "Алгебра и геометрия" in call.user and "Консультации в активной" not in call.user


def test_invalid_json_is_retried_with_error_in_prompt() -> None:
    client = FakeLLMClient(replies=["{не json", json.dumps(PREREQ, ensure_ascii=False)])
    result = extract_with_llm(MD, "rpd.md", client, tasks=["prerequisites"])
    assert len(result.prerequisites) == 1 and result.warnings == []
    assert "не принят" in client.calls[1].user and "не принят" not in client.calls[0].user


def test_gives_up_after_retries_with_warning() -> None:
    client = FakeLLMClient(respond=lambda call: "{}")  # нет обязательного поля items
    result = extract_with_llm(MD, "rpd.md", client, tasks=["prerequisites"])
    assert len(client.calls) == MAX_RETRIES + 1
    assert result.prerequisites == []
    assert "после 3 попыток" in result.warnings[0]


def test_hallucinated_quote_is_dropped_with_warning() -> None:
    bad = {"items": [{**PREREQ["items"][0], "quote": "курс квантовой механики"}]}
    client = FakeLLMClient(replies=[json.dumps(bad, ensure_ascii=False)])
    result = extract_with_llm(MD, "rpd.md", client, tasks=["prerequisites"])
    assert result.prerequisites == []
    assert "цитата не найдена" in result.warnings[0]


def test_total_hours_not_in_text_is_not_trusted() -> None:
    reply = json.dumps({**ACTIVE, "total_hours": 999}, ensure_ascii=False)
    result = extract_with_llm(MD, "rpd.md", FakeLLMClient(replies=[reply]), tasks=["active_forms"])
    assert result.active_total_hours is None
    assert any("не найден в тексте" in w for w in result.warnings)


def test_document_without_sections_makes_no_calls() -> None:
    client = FakeLLMClient(respond=_by_prompt)
    result = extract_with_llm("# Пусто\n\nтекст\n", "x.md", client)
    assert client.calls == [] and result.warnings == []


# --- подключение к extract_rpd -------------------------------------------------------------


def test_extract_rpd_without_llm_is_offline_and_has_no_llm_part() -> None:
    from edu_doc_agent.extraction import extract_rpd

    assert extract_rpd(MD, "x.md").llm is None


def test_extract_rpd_with_llm_adds_semantic_fields_and_keeps_rules() -> None:
    from edu_doc_agent.extraction import extract_rpd

    client = FakeLLMClient(respond=_by_prompt)
    result = extract_rpd(MD, "x.md", llm=client)
    assert result.llm is not None
    assert [p.name for p in result.llm.prerequisites] == ["алгебра и геометрия"]
    # правила (Yargy) работают независимо от LLM
    assert {"Алгебра и геометрия", "Основы дискретной математики"} <= {
        p.name for p in result.prerequisites
    }
    assert len(client.calls) == 3


def test_llm_warnings_and_disagreement_with_table_reach_result_warnings() -> None:
    from edu_doc_agent.extraction import extract_rpd

    bad = {"items": [{**PREREQ["items"][0], "quote": "курс квантовой механики"}]}
    active = {**ACTIVE, "total_hours": 34}  # в 1.4 такого числа нет
    replies = {"пререквизиты": bad, "активных и интерактивных": active}

    def respond(call: LLMCall) -> str:
        for key, data in replies.items():
            if key in call.user:
                return json.dumps(data, ensure_ascii=False)
        return json.dumps(RULES)

    result = extract_rpd(MD, "x.md", llm=FakeLLMClient(respond=respond))
    assert any(w.startswith("LLM: prerequisites: цитата не найдена") for w in result.warnings)
    assert any("не найден в тексте" in w for w in result.warnings)


def test_llm_total_that_differs_from_table_2_1_is_reported() -> None:
    from edu_doc_agent.extraction import extract_rpd

    text = MD.replace("Консультации в активной форме – 2 часа.", "Объём составляет 10 часов.")
    active = {"total_hours": 10, "items": []}

    def respond(call: LLMCall) -> str:
        if "активных и интерактивных" in call.user:
            return json.dumps(active)
        return json.dumps(PREREQ if "пререквизиты" in call.user else RULES, ensure_ascii=False)

    result = extract_rpd(text, "x.md", llm=FakeLLMClient(respond=respond))
    assert result.llm.active_total_hours == 10
    assert any("не совпадает с таблицей 2.1 (34)" in w for w in result.warnings)
