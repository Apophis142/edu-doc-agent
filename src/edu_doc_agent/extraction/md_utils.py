"""Разбор Markdown: таблицы с привязкой к разделу и очистка текста ячеек."""

import re
from dataclasses import dataclass

_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—−"})
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


@dataclass
class MdTable:
    rows: list[list[str]]
    row_lines: list[int]  # 1-based номер строки md для каждой строки rows
    section: str | None


def clean_text(text: str) -> str:
    """Убирает `<br>`-разметку и нормализует пробелы и тире.

    `<br>` (так парсер docx записывает перенос строки в ячейке) превращается в «\\n».
    Сами коды (в том числе нумерацию ПКП) не меняем — только символы-тире и пробелы.
    """
    text = _BR_RE.sub("\n", text)
    text = text.replace(" ", " ").translate(_DASHES)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def split_row(line: str) -> list[str]:
    s = line.strip()
    s = s.removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def _is_separator(cells: list[str]) -> bool:
    return all(not c or _SEPARATOR_CELL_RE.match(c) for c in cells) and any(cells)


def parse_tables(text: str) -> list[MdTable]:
    """Находит все pipe-таблицы; строки-разделители пропускает."""
    tables: list[MdTable] = []
    section: str | None = None
    rows: list[list[str]] = []
    row_lines: list[int] = []
    table_section: str | None = None

    def flush() -> None:
        nonlocal rows, row_lines
        if rows:
            tables.append(MdTable(rows=rows, row_lines=row_lines, section=table_section))
        rows, row_lines = [], []

    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("|"):
            if not rows:
                table_section = section
            cells = split_row(line)
            if not _is_separator(cells):
                rows.append(cells)
                row_lines.append(lineno)
            continue
        flush()
        m = _HEADING_RE.match(line)
        if m:
            section = clean_text(m.group(2))
    flush()
    return tables
