"""Тесты извлечения из РПД: синтетическая фикстура и (если есть) реальные md из data/md."""

import os
import re
from pathlib import Path

import pytest

from edu_doc_agent.extraction import RPDExtraction, extract_rpd, extract_rpd_file
from edu_doc_agent.extraction.md_utils import clean_text, parse_tables
from edu_doc_agent.extraction.patterns import COMPETENCE_RE, INDICATOR_RE, OUTCOME_RE

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "rpd_synthetic.md"
_DATA = Path(os.environ.get("DATA_DIR") or REPO_ROOT / "data")
# md_all/rpd — все РПД корпуса; md — небольшой набор из пяти документов
REAL_MD_DIR = _DATA / "md_all" / "rpd" if (_DATA / "md_all" / "rpd").exists() else _DATA / "md"
REAL_RPD = sorted(REAL_MD_DIR.glob("*.md")) if REAL_MD_DIR.exists() else []

needs_real_data = pytest.mark.skipif(
    not REAL_RPD, reason=f"нет реальных md-файлов РПД в {REAL_MD_DIR}"
)


# --- коды ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["УК-1", "ОПК-2", "ПКА-1", "УНК-3", "УКБ-2", "ПКП-ППК-ОС3", "ПКП-УНК-01", "ПКП-16-ППК-ОС3"],
)
def test_competence_code_full_match(text: str) -> None:
    m = COMPETENCE_RE.search(text)
    assert m and m.group(0) == text


def test_codes_are_not_normalized() -> None:
    assert COMPETENCE_RE.search("ПКП-ППК-ОС3").group(0) != COMPETENCE_RE.search(
        "ПКП-16-ППК-ОС3"
    ).group(0)


def test_indicator_and_outcome_codes() -> None:
    assert INDICATOR_RE.search("ПКП-УНК-03.01. З-1").group(0) == "ПКП-УНК-03.01"
    assert OUTCOME_RE.search("ПКП-ППК-ОС3.1. З-2. Знает").group(0) == "ПКП-ППК-ОС3.1. З-2"
    assert OUTCOME_RE.search("ПКП-ППК-Р2.1. 3-1. Знает")  # опечатка: цифра 3 вместо З
    assert not INDICATOR_RE.search("ПОДУК-1.2")  # код внутри слова не считаем


def test_clean_text_normalizes_markup_and_dashes() -> None:
    assert clean_text("**ПКП–ППК—Р1**  <u>x</u>") == "ПКП-ППК-Р1 x"


def test_parse_tables_keeps_line_numbers_and_sections() -> None:
    md = "# A\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\ntext\n\n## B\n| c |\n"
    t1, t2 = parse_tables(md)
    assert t1.rows == [["a", "b"], ["1", "2"]] and t1.row_lines == [3, 5] and t1.section == "A"
    assert t2.rows == [["c"]] and t2.section == "B"


# --- синтетический РПД -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic() -> RPDExtraction:
    return extract_rpd_file(FIXTURE)


def test_synthetic_title_block(synthetic: RPDExtraction) -> None:
    assert synthetic.doc_kind == "discipline"
    assert synthetic.title == "Синтетическая дисциплина"
    assert synthetic.title_en == "Synthetic Discipline"
    assert synthetic.registration_number == "000123"
    assert synthetic.credits == 3.0
    assert synthetic.warnings == []


def test_synthetic_competences(synthetic: RPDExtraction) -> None:
    got = {c.code: c.name for c in synthetic.competences}
    assert got == {
        "ПКП-ППК-ТС1": "Способен проектировать синтетические системы",
        "ОПК-9": "Способен применять тестовые методы",
        "ПКП-16-ППК-ТС2": "способен оценивать качество",
    }


def test_synthetic_indicators(synthetic: RPDExtraction) -> None:
    by_code = {i.code: i for i in synthetic.indicators}
    assert list(by_code) == [
        "ПКП-ППК-ТС1.1",
        "ПКП-ППК-ТС1.2",
        "ОПК-9.1",
        "ОПК-9.2",
        "ПКП-ППК-ТС2.1",
    ]
    assert by_code["ПКП-ППК-ТС1.1"].level == "Средний"
    assert by_code["ПКП-ППК-ТС1.1"].text == "Строит модели систем"
    # в строке без столбца компетенции компетенция берётся из предыдущей строки
    assert by_code["ОПК-9.2"].competence_code == "ОПК-9"
    assert by_code["ПКП-ППК-ТС1.2"].competence_code == "ПКП-ППК-ТС1"


def test_synthetic_outcomes_all_styles(synthetic: RPDExtraction) -> None:
    outs = synthetic.learning_outcomes
    # префиксный код + маркеры `*`
    first = [o for o in outs if o.indicator_code == "ПКП-ППК-ТС1.1"]
    assert [(o.kind, o.code) for o in first] == [
        ("знает", "ПКП-ППК-ТС1.1. З-1"),
        ("знает", "ПКП-ППК-ТС1.1. З-2"),
        ("умеет", "ПКП-ППК-ТС1.1. У-1"),
    ]
    assert first[0].text == "Знает устройство синтетических систем."
    # суффиксный код в скобках, маркеры `•`
    second = [o for o in outs if o.indicator_code == "ПКП-ППК-ТС1.2"]
    assert [o.text for o in second] == ["основы тестирования", "виды проверок", "писать тесты"]
    # без кодов вообще: вид берётся из заголовка «знает:/умеет:/владеет:»
    plain = [o for o in outs if o.competence_code == "ОПК-9"]
    assert all(o.code is None for o in plain)
    assert [o.kind for o in plain] == ["знает", "умеет", "знает", "владеет"]
    # код без маркеров списка и опечатка «3-1»
    third = [o for o in outs if o.competence_code == "ПКП-16-ППК-ТС2"]
    assert [(o.kind, o.code) for o in third] == [
        ("знает", "ПКП-16-ППК-ТС2.1. 3-1"),
        ("умеет", "ПКП-16-ППК-ТС2.1. У-1"),
    ]


def test_synthetic_assessments(synthetic: RPDExtraction) -> None:
    got = {a.indicator_code: a.materials for a in synthetic.assessments}
    assert got == {
        "ПКП-ППК-ТС1.1": ["Практические занятия 1-2", "тест", "вопросы к зачёту"],
        "ПКП-ППК-ТС1.2": ["Семинар 3"],
        "ОПК-9.1": ["Вопросы к экзамену"],
    }


def test_synthetic_control_forms(synthetic: RPDExtraction) -> None:
    got = [
        (f.semester, f.current, [(a.kind, a.details) for a in f.intermediate])
        for f in synthetic.control_forms
    ]
    assert got == [
        (3, ["практические работы", "тесты"], [("зачёт с оценкой", [])]),
        (4, [], [("экзамен", [])]),
    ]
    assert synthetic.control_forms[0].current_raw == "практические работы, тесты"


def test_source_points_to_real_line(synthetic: RPDExtraction) -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    for ind in synthetic.indicators:
        assert ind.code in lines[ind.source.line - 1]
        assert ind.source.section.startswith("1.3.")


def test_missing_tables_give_warnings() -> None:
    result = extract_rpd("# Пусто\n\nтекст", file="x.md")
    assert len(result.warnings) == 3 and not result.competences


# --- регрессии: случаи, найденные на реальном корпусе ---------------------------------------

HEAD = (
    "| Код и наименование компетенции | Планируемые результаты обучения | Код индикатора |\n"
    "| --- | --- | --- |\n"
)


def _title_doc(title: str) -> str:
    return (
        f"**Р А Б О Ч А Я П Р О Г Р А М М А**\n\n**учебной дисциплины**\n\n*{title}*\n\n*Eng*\n\n"
        "**Язык(и) обучения**\n\nрусский\n"
    )


def test_title_starting_with_word_yazyk_is_not_mistaken_for_language_line() -> None:
    assert (
        extract_rpd(_title_doc("Языки программирования"), "x.md").title == "Языки программирования"
    )


def test_outcomes_table_row_without_outcomes_column() -> None:
    md = HEAD + "| ОПК-1 Способен применять знания | ОПК-1.2 Использует знания |\n"
    r = extract_rpd(md, "x.md")
    assert [(c.code, c.name) for c in r.competences] == [("ОПК-1", "Способен применять знания")]
    assert [i.code for i in r.indicators] == ["ОПК-1.2"] and r.learning_outcomes == []


def test_outcomes_table_with_number_and_group_columns() -> None:
    md = (
        "| № | Группа | Код и наименование компетенции "
        "| Планируемые результаты обучения | Индикатор |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 1 | ОПК | ОПК-1: Способен применять знания "
        "| Знать основы; Уметь считать; | ОПК-1.1. Умеет |\n"
    )
    r = extract_rpd(md, "x.md")
    assert r.competences[0].code == "ОПК-1" and r.competences[0].name == "Способен применять знания"
    assert [(o.kind, o.text) for o in r.learning_outcomes] == [
        ("знает", "Знать основы"),
        ("умеет", "Уметь считать"),
    ]


def test_competence_name_before_code_and_kind_headings_without_colon() -> None:
    md = (
        HEAD
        + "| способен проектировать (ПКП-МО-1) "
        + "| **знать**   * основы ML   **уметь**   * обучать модели "
        + "| ПКП-МО-1.1 Применяет |\n"
    )
    r = extract_rpd(md, "x.md")
    assert (r.competences[0].code, r.competences[0].name) == ("ПКП-МО-1", "способен проектировать")
    assert [(o.kind, o.text) for o in r.learning_outcomes] == [
        ("знает", "основы ML"),
        ("умеет", "обучать модели"),
    ]


def test_indicators_sharing_one_text() -> None:
    md = HEAD + "| ОПК-1. Способен | * Знает основы. | * ОПК-1.1; ОПК-1.2: применяет знания. |\n"
    r = extract_rpd(md, "x.md")
    assert [(i.code, i.text) for i in r.indicators] == [
        ("ОПК-1.1", "применяет знания"),
        ("ОПК-1.2", "применяет знания"),
    ]


ASSESS_HEAD = (
    "| № | Код индикатора | Контрольно-измерительные материалы (КИМ) |\n| --- | --- | --- |\n"
)


def test_assessment_rows_continuation_multi_indicator_and_empty_kim() -> None:
    md = (
        ASSESS_HEAD
        + "| 1 | ОПК-1.1 Первый | Тест; Экзамен |\n"
        + "|  | ОПК-1.2 Второй | Тест |\n"
        + "| 2 | УК-1.1 Один  УК-1.2 Два | Контрольная |\n"
        + "| 3 | ОПК-2.1 Без КИМ |\n"
    )
    r = extract_rpd(md, "x.md")
    assert [(a.indicator_code, a.materials) for a in r.assessments] == [
        ("ОПК-1.1", ["Тест", "Экзамен"]),
        ("ОПК-1.2", ["Тест"]),
        ("УК-1.1", ["Контрольная"]),
        ("УК-1.2", ["Контрольная"]),
        ("ОПК-2.1", []),
    ]


# --- реальные документы (пропускаются, если data/md нет) ---------------------------------------


@needs_real_data
@pytest.mark.parametrize("path", REAL_RPD, ids=lambda p: p.stem)
def test_real_rpd_parser_invariants(path: Path) -> None:
    """Что должен найти парсер в любом РПД. Полнота оценочных средств и названий компетенций —
    свойство документа, а не парсера, поэтому здесь не проверяется."""
    r = extract_rpd_file(path)
    assert r.doc_kind == "discipline" and r.title
    assert r.registration_number and re.fullmatch(r"\d{5,6}", r.registration_number)
    assert r.credits and r.credits > 0
    assert r.competences and r.indicators and r.learning_outcomes and r.control_forms
    assert all(INDICATOR_RE.fullmatch(i.code) for i in r.indicators)
    assert all(o.competence_code and o.kind for o in r.learning_outcomes)
    assert all(f.intermediate for f in r.control_forms)


@needs_real_data
def test_real_corpus_has_no_unclassified_outcomes() -> None:
    for path in REAL_RPD:
        r = extract_rpd_file(path)
        assert r.competences, path.name
        assert all(o.kind for o in r.learning_outcomes), path.name


@needs_real_data
def test_real_devops_exact_values() -> None:
    path = next((p for p in REAL_RPD if "DevOps" in p.name or "devops" in p.name), None)
    if path is None:
        pytest.skip("нет DevOps в корпусе")
    r = extract_rpd_file(path)
    assert (r.title, r.registration_number, r.credits) == ("DevOps", "082922", 4.0)
    assert [c.code for c in r.competences] == [
        "ПКП-ППК-ОС3",
        "ПКП-ППК-ОС4",
        "ПКП-ППК-ОС6",
        "ПКП-ППК-Р5",
        "ПКП-ППК-ДА6",
    ]
    assert len(r.indicators) == 12 and len(r.assessments) == 12
    assert all(o.code for o in r.learning_outcomes)  # в этом шаблоне у каждого пункта есть код
    assert [(f.semester, [a.kind for a in f.intermediate]) for f in r.control_forms] == [
        (5, ["экзамен"])
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("экзамен", [("экзамен", [])]),
        ("Зачет", [("зачёт", [])]),
        ("зачет, экзамен", [("зачёт", []), ("экзамен", [])]),
        ("зачёт, устно, традиционная форма", [("зачёт", ["устно", "традиционная форма"])]),
        (
            "зачёт, устно, по результатам работы в семестре, экзамен, устно, традиционная форма",
            [
                ("зачёт", ["устно", "по результатам работы в семестре"]),
                ("экзамен", ["устно", "традиционная форма"]),
            ],
        ),
        ("зачёт (защита проекта)", [("зачёт", ["защита проекта"])]),
        ("дифференцированный зачёт", [("дифференцированный зачёт", [])]),
    ],
)
def test_parse_attestations(raw: str, expected: list) -> None:
    from edu_doc_agent.extraction.rpd import _parse_attestations

    assert [(a.kind, a.details) for a in _parse_attestations(raw)] == expected


def test_split_items_ignores_commas_in_parentheses_and_drops_repeats() -> None:
    from edu_doc_agent.extraction.rpd import _split_items

    assert _split_items("а (б, в), г; г") == ["а (б, в)", "г"]
    assert _split_items(None) == []
