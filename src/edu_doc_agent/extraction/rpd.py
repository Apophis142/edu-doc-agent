"""Извлечение сущностей из Markdown-версии РПД/РПП регулярными выражениями.

Что берём:
- титул: название, рег. номер, трудоёмкость, тип документа;
- таблица 1.3: компетенции, индикаторы, результаты обучения;
- таблица 3.1.4: индикатор → контрольно-измерительные материалы (оценочные средства);
- таблица форм контроля: текущий контроль и промежуточная аттестация по семестрам.

Всё, что не удалось разобрать правилами, не выдумываем, а пропускаем и пишем в `warnings`
(кандидаты на LLM-извлечение).
"""

from pathlib import Path

from edu_doc_agent.extraction.md_utils import MdTable, clean_text, parse_tables, strip_emphasis
from edu_doc_agent.extraction.models import (
    AssessmentLink,
    Attestation,
    Competence,
    ControlForm,
    Indicator,
    LearningOutcome,
    OutcomeKind,
    RPDExtraction,
    SourceRef,
)
from edu_doc_agent.extraction.patterns import (
    ATTESTATION_KIND_RE,
    BULLET_RE,
    COMPETENCE_CELL_RE,
    CREDITS_RE,
    INDICATOR_RE,
    INTERMEDIATE_RE,
    KIND_BY_LETTER,
    KIND_CANONICAL,
    KIND_HEADING_RE,
    KIND_SPLIT_RE,
    KIND_WORD_RE,
    LANGUAGE_LINE_RE,
    LEVEL_RE,
    NAME_THEN_CODE_RE,
    OUTCOME_RE,
    REG_NUMBER_RE,
    SEMESTER_ROW_RE,
    SUFFIX_OUTCOME_RE,
)

_TITLE_SCAN_LINES = 40


def extract_rpd_file(path: Path) -> RPDExtraction:
    return extract_rpd(path.read_text(encoding="utf-8"), file=path.name)


def extract_rpd(text: str, file: str) -> RPDExtraction:
    result = RPDExtraction(file=file)
    _extract_title_block(text, result)

    tables = parse_tables(text)
    outcome_tables = [t for t in tables if "планируемые результаты" in _header(t)]
    assessment_tables = [
        t for t in tables if "измерительные" in _header(t) and t not in outcome_tables
    ]
    for table in outcome_tables:
        _extract_outcome_table(table, file, result)
    for table in assessment_tables:
        _extract_assessment_table(table, file, result)
    for table in tables:
        _extract_control_forms(table, file, result)

    if not outcome_tables:
        result.warnings.append("не найдена таблица результатов обучения (1.3)")
    if not assessment_tables:
        result.warnings.append("не найдена таблица оценочных средств (3.1.4)")
    if not result.control_forms:
        result.warnings.append("не найдены формы контроля по семестрам")
    return result


# --- титул ---------------------------------------------------------------------------------


def _extract_title_block(text: str, result: RPDExtraction) -> None:
    head = text.splitlines()[:_TITLE_SCAN_LINES]
    plain = clean_text("\n".join(head))
    if m := CREDITS_RE.search(plain):
        result.credits = float(m.group(1).replace(",", "."))
    if m := REG_NUMBER_RE.search(plain):
        result.registration_number = m.group(1)

    lines: list[str] = []
    for raw in head:
        line = strip_emphasis(raw)
        if LANGUAGE_LINE_RE.match(line):
            break
        if line:
            lines.append(line)
    idx = next((i for i, ln in enumerate(lines) if _squash(ln) == "РАБОЧАЯПРОГРАММА"), None)
    if idx is None or idx + 1 >= len(lines):
        return
    rest = lines[idx + 1 :]
    if "дисциплины" in rest[0].lower():
        result.doc_kind = "discipline"
    elif _squash(rest[0]) == "ПРАКТИКИ":
        result.doc_kind = "practice"
    else:
        return
    if len(rest) > 1:
        result.title = rest[1]
    if len(rest) > 2:
        result.title_en = rest[2]


def _squash(s: str) -> str:
    return "".join(s.split()).upper()


# --- таблицы ------------------------------------------------------------------------------


def _header(table: MdTable) -> str:
    """Текст первых строк таблицы в нижнем регистре, для опознания таблицы по заголовку."""
    return clean_text(" ".join(c for row in table.rows[:3] for c in row)).lower()


def _ref(table: MdTable, row_idx: int, file: str) -> SourceRef:
    return SourceRef(file=file, section=table.section, line=table.row_lines[row_idx])


def _extract_outcome_table(table: MdTable, file: str, result: RPDExtraction) -> None:
    competences = {c.code: c for c in result.competences}
    seen_indicators = {(i.code, i.competence_code) for i in result.indicators}
    current_code: str | None = None

    header = _outcome_header(table)
    if header is None:
        return
    header_idx, ncols, comp_col, out_col, ind_col = header

    for idx, row in enumerate(table.rows):
        if idx <= header_idx:
            continue
        shift = max(0, ncols - len(row))  # в части строк левые столбцы пропущены

        def cell(col: int | None, row: list[str] = row, shift: int = shift) -> str:
            j = None if col is None else col - shift
            return row[j] if j is not None and 0 <= j < len(row) else ""

        comp_cell, out_cell, ind_cell = cell(comp_col), cell(out_col), cell(ind_col)
        if shift and _looks_like_competence(out_cell):
            # в строке нет столбца результатов: левая ячейка — компетенция, а не результаты
            comp_cell, out_cell = out_cell, ""
        if not out_cell.strip() and not ind_cell.strip():
            continue
        ref = _ref(table, idx, file)

        if parsed := _parse_competence_cell(comp_cell):
            current_code, name = parsed
            known = competences.get(current_code)
            if known is None:
                competences[current_code] = Competence(code=current_code, name=name, source=ref)
            elif known.name is None and name:
                known.name = name

        for code, text, level in _parse_indicators(ind_cell):
            if (code, current_code) not in seen_indicators:
                seen_indicators.add((code, current_code))
                result.indicators.append(
                    Indicator(
                        code=code, competence_code=current_code, text=text, level=level, source=ref
                    )
                )
        for kind, code, text in _parse_outcomes(out_cell):
            result.learning_outcomes.append(
                LearningOutcome(
                    kind=kind,
                    code=code,
                    indicator_code=_indicator_of(code),
                    competence_code=current_code,
                    text=text,
                    source=ref,
                )
            )
    result.competences = list(competences.values())


def _outcome_header(table: MdTable) -> tuple[int, int, int | None, int, int | None] | None:
    """Строка-заголовок таблицы 1.3 и индексы столбцов: компетенция, результаты, индикатор."""
    for i, row in enumerate(table.rows[:4]):
        low = [clean_text(c).lower() for c in row]
        outs = [j for j, c in enumerate(low) if "планируемые результаты" in c]
        if not outs:
            continue
        comps = [
            j
            for j, c in enumerate(low)
            if "компетенц" in c and "планируемые" not in c and "индикатор" not in c
        ]
        comp = next((j for j in comps if "код" in low[j]), comps[0] if comps else None)
        ind = next((j for j, c in enumerate(low) if "индикатор" in c), None)
        return i, len(row), comp, outs[0], ind
    return None


def _looks_like_competence(cell: str) -> bool:
    text = clean_text(cell)
    return bool(
        (COMPETENCE_CELL_RE.match(text) or NAME_THEN_CODE_RE.match(text))
        and not KIND_HEADING_RE.search(text)
        and not OUTCOME_RE.search(text)
    )


def _parse_competence_cell(cell: str) -> tuple[str, str | None] | None:
    text = clean_text(cell)
    if m := COMPETENCE_CELL_RE.match(text):
        return m.group(1), clean_text(m.group(2) or "") or None
    if m := NAME_THEN_CODE_RE.match(text):
        return m.group(2), clean_text(m.group(1)) or None
    return None


def _parse_indicators(cell: str) -> list[tuple[str, str, str | None]]:
    text = clean_text(cell)
    outcome_spans = [m.span() for m in OUTCOME_RE.finditer(text)]
    found = [
        m
        for m in INDICATOR_RE.finditer(text)
        if not any(s <= m.start() < e for s, e in outcome_spans)
    ]
    items = []
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        body = text[m.end() : end].strip().lstrip(".:;,* ").strip()
        level = None
        if lm := LEVEL_RE.search(body):
            level = lm.group(1).capitalize()
            body = body[: lm.start()].strip()
        items.append((m.group(0), body.rstrip(". ;").strip(), level))
    # «ОПК-1.1; ОПК-1.2: текст» — у первого кода текста нет, берём общий
    for i in range(len(items) - 2, -1, -1):
        if not items[i][1]:
            items[i] = (items[i][0], items[i + 1][1], items[i + 1][2])
    return items


def _indicator_of(outcome_code: str | None) -> str | None:
    if outcome_code and (m := INDICATOR_RE.match(outcome_code)):
        return m.group(0)
    return None


def _parse_outcomes(cell: str) -> list[tuple[OutcomeKind | None, str | None, str]]:
    text = clean_text(cell)
    heads = list(KIND_HEADING_RE.finditer(text))
    groups: list[tuple[OutcomeKind | None, str]] = []
    if not heads:
        groups.append((None, text))
    else:
        if text[: heads[0].start()].strip():
            groups.append((None, text[: heads[0].start()]))
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            groups.append((KIND_CANONICAL[h.group(1).lower()], text[h.end() : end]))  # type: ignore[arg-type]

    out: list[tuple[OutcomeKind | None, str | None, str]] = []
    for kind, body in groups:
        for chunk in BULLET_RE.split(body):
            for item in _split_by_codes(chunk):
                parsed = _parse_outcome_item(item, kind)
                if parsed:
                    out.append(parsed)
    return out


def _split_by_codes(chunk: str) -> list[str]:
    """Режет кусок на пункты: по кодам результатов, а без кодов — по словам «Знать/Уметь»."""
    suffix = list(SUFFIX_OUTCOME_RE.finditer(chunk))
    if len(suffix) > 1:  # «текст (КОД); текст (КОД)»
        cuts = [m.end() for m in suffix[:-1]]
    else:  # «КОД. текст КОД. текст»
        leading = [
            m.start()
            for m in OUTCOME_RE.finditer(chunk)
            if not chunk[: m.start()].rstrip().endswith("(")
        ]
        cuts = [p for p in leading if p > 0] if len(leading) > 1 else []
    if not cuts and not OUTCOME_RE.search(chunk):
        return [p for p in KIND_SPLIT_RE.split(chunk) if p.strip()]
    pieces, prev = [], 0
    for c in cuts:
        pieces.append(chunk[prev:c])
        prev = c
    pieces.append(chunk[prev:])
    return [p for p in pieces if p.strip()]


def _parse_outcome_item(
    item: str, kind: OutcomeKind | None
) -> tuple[OutcomeKind | None, str | None, str] | None:
    code: str | None = None
    if m := SUFFIX_OUTCOME_RE.search(item):
        code = m.group(1)
        item = item[: m.start()] + item[m.end() :]
    elif m := OUTCOME_RE.search(item):
        code = m.group(0)
        item = item[: m.start()] + item[m.end() :]
    text = " ".join(item.split()).strip(" ;").lstrip(". ").strip()
    if len(text) < 3:
        return None
    if code:
        code = " ".join(code.split())
        kind = kind or KIND_BY_LETTER.get(code[-3])  # type: ignore[assignment]
    if kind is None and (m := KIND_WORD_RE.match(text)):
        kind = KIND_CANONICAL[m.group(1).lower()]  # type: ignore[assignment]
    return kind, code, text


def _extract_assessment_table(table: MdTable, file: str, result: RPDExtraction) -> None:
    for idx, row in enumerate(table.rows):
        if not row:
            continue
        number = clean_text(row[0]).rstrip(".)")
        filled = [clean_text(c) for c in row[1:] if clean_text(c)]
        if number and not number.isdigit():
            continue  # заголовок и прочие служебные строки
        if len(filled) >= 2:
            indicator_text, materials = " ".join(filled[:-1]), filled[-1]
        elif len(filled) == 1 and INDICATOR_RE.search(filled[0]):
            indicator_text, materials = filled[0], ""  # КИМ в строке не указаны
        else:
            continue
        indicators = _parse_indicators(indicator_text)
        if not number and not indicators:
            continue  # строка без номера — продолжение, только если в ней есть индикатор
        # в одной строке может быть несколько индикаторов с общими материалами
        for code, text in [(c, t) for c, t, _ in indicators] or [(None, indicator_text)]:
            result.assessments.append(
                AssessmentLink(
                    indicator_code=code,
                    indicator_text=text,
                    materials_raw=materials,
                    materials=[p.strip() for p in materials.split(";") if p.strip()],
                    source=_ref(table, idx, file),
                )
            )


def _extract_control_forms(table: MdTable, file: str, result: RPDExtraction) -> None:
    in_forms = False
    for idx, row in enumerate(table.rows):
        if any("формы текущего контроля" in c.lower() for c in row):
            in_forms = True
            continue
        if not in_forms:
            continue
        m = SEMESTER_ROW_RE.match(clean_text(row[0])) if row else None
        if not m:
            continue
        values: list[str] = []
        for c in row[1:]:
            c = clean_text(c)
            if c and c not in values:
                values.append(c)
        intermediate_raw = "; ".join(v for v in values if INTERMEDIATE_RE.match(v)) or None
        current_raw = "; ".join(v for v in values if not INTERMEDIATE_RE.match(v)) or None
        form = ControlForm(
            semester=int(m.group(1)),
            current=_split_items(current_raw),
            intermediate=_parse_attestations(intermediate_raw),
            current_raw=current_raw,
            intermediate_raw=intermediate_raw,
            source=_ref(table, idx, file),
        )
        key = (form.semester, form.current_raw, form.intermediate_raw)
        if all(
            (f.semester, f.current_raw, f.intermediate_raw) != key for f in result.control_forms
        ):
            result.control_forms.append(form)


def _split_items(raw: str | None) -> list[str]:
    """Режет «a, b; c» по запятым и «;» вне скобок; повторы убирает."""
    if not raw:
        return []
    items, depth, buf = [], 0, ""
    for ch in raw:
        depth += (ch == "(") - (ch == ")")
        if ch in ",;" and depth <= 0:
            items.append(buf)
            buf = ""
        else:
            buf += ch
    items.append(buf)
    out: list[str] = []
    for item in (i.strip() for i in items):
        if item and item not in out:
            out.append(item)
    return out


def _parse_attestations(raw: str | None) -> list[Attestation]:
    """«зачёт, устно, ...; экзамен, устно» → [зачёт[устно, ...], экзамен[устно]]."""
    if not raw:
        return []
    found = list(ATTESTATION_KIND_RE.finditer(raw))
    result = []
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(raw)
        tail = raw[m.end() : end].strip(" ,;:")
        details = _split_items(tail.replace("(", ", ").replace(")", ""))
        kind = " ".join(m.group(0).lower().replace("ё", "е").split()).replace("зачет", "зачёт")
        result.append(Attestation(kind=kind, details=details))
    return result
