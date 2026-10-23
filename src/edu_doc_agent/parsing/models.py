from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

_MD_LINE_START = ("#", "*", "+", "-", ">", "|", "=")


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"


@dataclass
class Block:
    kind: BlockKind
    text: str = ""
    level: int = 0  # заголовок
    number: str = ""  # нумерация
    rows: list[list[str]] = field(default_factory=list)  # таблица

    def to_markdown(self) -> str:
        if self.kind == BlockKind.HEADING:
            return "#" * min(max(self.level, 1), 6) + " " + f"{self.number} {self.text}".strip()
        if self.kind == BlockKind.LIST_ITEM:
            return f"{self.number or '-'} {_escape(self.text)}"
        if self.kind == BlockKind.TABLE:
            header, *body = self.rows
            lines = [_md_row(header), _md_row(["---"] * len(header))]
            return "\n".join(lines + [_md_row(row) for row in body])
        return _escape(self.text)


def _escape(text: str) -> str:
    return "\\" + text if text.startswith(_MD_LINE_START) else text


def _md_row(cells: list[str]) -> str:
    cells = [c.replace("|", r"\|").replace("\n", "<br>") for c in cells]
    return "| " + " | ".join(cells) + " |"


@dataclass
class ParsedDocument:
    source: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def tables(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == BlockKind.TABLE]

    def to_markdown(self) -> str:
        parts = []
        depth = -1
        for b in self.blocks:
            if b.kind == BlockKind.LIST_ITEM:
                depth = min(b.level, depth + 1)
                parts.append("   " * depth + b.to_markdown())
            else:
                depth = -1
                parts.append(b.to_markdown())
        return "\n\n".join(parts) + "\n"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseParser(ABC):
    """Парсер конкретного формата"""

    @abstractmethod
    def parse(self, path: Path) -> ParsedDocument: ...
