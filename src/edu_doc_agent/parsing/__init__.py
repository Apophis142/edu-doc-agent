"""Parser Service: документы ОП -> ParsedDocument (список блоков) -> Markdown"""

from edu_doc_agent.parsing.models import Block, BlockKind, ParsedDocument
from edu_doc_agent.parsing.registry import (
    UnsupportedFormatError,
    parse_document,
    supported_suffixes,
)

__all__ = [
    "Block",
    "BlockKind",
    "ParsedDocument",
    "UnsupportedFormatError",
    "parse_document",
    "supported_suffixes",
]
