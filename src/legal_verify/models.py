from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class CitationStatus(str, Enum):
    CONFIRMED = "confirmed"   # Текст совпадает с источником
    MISMATCH  = "mismatch"    # Текст расходится с актуальной редакцией
    NOT_FOUND = "not_found"   # Не удалось найти/подтвердить
    MISSING   = "missing"     # НПА упомянут в тексте, но цитата отсутствует


class Citation(BaseModel):
    id:          int
    title:       str                    # «п. 1 ст. 224 НК РФ»
    text:        str                    # Полный текст цитаты
    status:      CitationStatus | None = None
    actual_text: str | None = None      # Актуальный текст (если mismatch)
    source_url:  str | None = None      # URL источника


class LegalAnswer(BaseModel):
    question:    str
    brief:       str                    # Блок 1: Краткий ответ
    explanation: str                    # Блок 2: Пояснение
    citations:   list[Citation]         # Блок 3: Цитаты
    iteration:   int = 1
    verified:    bool = False


class CorrectionDiff(BaseModel):
    section:  str   # «Блок 1», «Блок 2», «Цитата 3»
    reason:   str
    old_text: str
    new_text: str


class VerificationReport(BaseModel):
    # Шаг A — детерминированные проверки (код)
    structure_ok:      bool
    structure_errors:  list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)  # НПА без цитаты
    orphan_citations:  list[str] = Field(default_factory=list)  # Цитаты без упоминания
    arithmetic_ok:     bool = True
    arithmetic_errors: list[str] = Field(default_factory=list)

    # Шаг Б — LLM-проверки
    citations_results: list[Citation] = Field(default_factory=list)
    correction_diffs:  list[CorrectionDiff] = Field(default_factory=list)

    # Сводка
    has_errors: bool
    summary:    str


# Промежуточная модель — то, что возвращает LLM-верификатор
class LLMVerificationResult(BaseModel):
    citations_results: list[Citation]
    correction_diffs:  list[CorrectionDiff] = Field(default_factory=list)
    summary:           str
