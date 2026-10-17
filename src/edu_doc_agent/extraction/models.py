"""Pydantic-модели результата извлечения из РПД.

Каждая сущность хранит `source` — откуда она взята (файл, раздел, строка),
чтобы в протоколе проверки можно было сослаться на источник.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OutcomeKind = Literal["знает", "умеет", "владеет"]
DocKind = Literal["discipline", "practice"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(_Model):
    """Место в исходном документе."""

    file: str
    section: str | None = None
    line: int | None = Field(default=None, description="Номер строки в md-файле, с 1")


class Competence(_Model):
    code: str
    name: str | None = None
    source: SourceRef


class Indicator(_Model):
    code: str
    competence_code: str | None = None
    text: str
    level: str | None = Field(default=None, description="Базовый / Средний / Продвинутый")
    source: SourceRef


class LearningOutcome(_Model):
    kind: OutcomeKind | None = None
    code: str | None = Field(
        default=None, description="Например, «ПКП-ППК-ОС3.1. З-1»; может не быть"
    )
    indicator_code: str | None = None
    competence_code: str | None = None
    text: str
    source: SourceRef


class AssessmentLink(_Model):
    """Строка таблицы «индикатор → контрольно-измерительные материалы»."""

    indicator_code: str | None = None
    indicator_text: str | None = None
    materials_raw: str
    materials: list[str] = Field(default_factory=list)
    source: SourceRef


class Attestation(_Model):
    """Одна промежуточная аттестация: вид и уточнения («экзамен», «устно, традиционная форма»)."""

    kind: str = Field(
        description="экзамен / зачёт / зачёт с оценкой (нормализовано: нижний регистр, ё)"
    )
    details: list[str] = Field(default_factory=list)


class ControlForm(_Model):
    semester: int
    current: list[str] = Field(default_factory=list, description="Формы текущего контроля")
    intermediate: list[Attestation] = Field(default_factory=list)
    current_raw: str | None = Field(default=None, description="Ячейка как в документе")
    intermediate_raw: str | None = Field(default=None, description="Ячейка как в документе")
    source: SourceRef


class RPDExtraction(_Model):
    file: str
    doc_kind: DocKind | None = None
    title: str | None = None
    title_en: str | None = None
    registration_number: str | None = None
    credits: float | None = None
    competences: list[Competence] = Field(default_factory=list)
    indicators: list[Indicator] = Field(default_factory=list)
    learning_outcomes: list[LearningOutcome] = Field(default_factory=list)
    assessments: list[AssessmentLink] = Field(default_factory=list)
    control_forms: list[ControlForm] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
