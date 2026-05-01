from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from . import config
from .models import (
    Citation,
    CitationStatus,
    CorrectionDiff,
    LegalAnswer,
    LLMVerificationResult,
    VerificationReport,
)

_PROMPT_PATH = config.PROMPTS_DIR / "verifier.md"
_VERIFIER_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Паттерн для извлечения ссылок на НПА из текста
# Примеры: «ч. 2 ст. 15 ТК РФ», «п. 1 ст. 420 НК РФ», «ФЗ от 12.07.2024 № 176-ФЗ»
_NPA_PATTERN = re.compile(
    r"""
    (?:
        (?:ч\.?\s*\d+\s+)?            # ч. 2
        (?:п\.?\s*\d+\s+)?            # п. 1
        (?:подп\.?\s*\d+\s+)?         # подп. 3
        ст\.?\s*\d+(?:\.\d+)?         # ст. 15 или ст. 15.1
        (?:\s+[А-ЯЁ]{1,5}\s+РФ)?     # ТК РФ
    )
    |
    (?:ФЗ\s+от\s+\d{2}\.\d{2}\.\d{4}\s+№\s*\d+-ФЗ)  # ФЗ от 12.07.2024 № 176-ФЗ
    """,
    re.VERBOSE | re.IGNORECASE,
)

# JSON-схема для ответа LLM-верификатора
_VERIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "citations_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":          {"type": "integer"},
                    "title":       {"type": "string"},
                    "text":        {"type": "string"},
                    "status":      {"type": "string", "enum": ["confirmed", "mismatch", "not_found"]},
                    "actual_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "source_url":  {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["id", "title", "text", "status", "actual_text", "source_url"],
                "additionalProperties": False,
            },
        },
        "correction_diffs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section":  {"type": "string"},
                    "reason":   {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["section", "reason", "old_text", "new_text"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["citations_results", "correction_diffs", "summary"],
    "additionalProperties": False,
}


class Verifier:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=config.require_openai_api_key())

    async def verify(self, answer: LegalAnswer) -> VerificationReport:
        # Шаг A: детерминированные проверки (без LLM)
        structure_ok, structure_errors = self._check_structure(answer)
        missing, orphans = self._check_citation_completeness(answer)
        arithmetic_ok, arithmetic_errors = self._check_arithmetic(answer)

        # Шаг Б: LLM-верификация актуальности цитат
        llm_result = await self._llm_verify(answer)

        has_errors = (
            not structure_ok
            or bool(missing)
            or not arithmetic_ok
            or any(
                c.status in (CitationStatus.MISMATCH, CitationStatus.NOT_FOUND)
                for c in llm_result.citations_results
            )
        )

        return VerificationReport(
            structure_ok=structure_ok,
            structure_errors=structure_errors,
            missing_citations=missing,
            orphan_citations=orphans,
            arithmetic_ok=arithmetic_ok,
            arithmetic_errors=arithmetic_errors,
            citations_results=llm_result.citations_results,
            correction_diffs=llm_result.correction_diffs,
            has_errors=has_errors,
            summary=llm_result.summary,
        )

    # ------------------------------------------------------------------
    # Шаг A: детерминированные проверки
    # ------------------------------------------------------------------

    def _check_structure(self, answer: LegalAnswer) -> tuple[bool, list[str]]:
        errors: list[str] = []

        if not answer.brief.strip():
            errors.append("Блок 1 (brief) пустой")
        if not answer.explanation.strip():
            errors.append("Блок 2 (explanation) пустой")
        if not answer.citations:
            errors.append("Блок 3 (citations) пустой — нет ни одной цитаты")

        # Проверяем нумерацию разделов в explanation
        if answer.explanation and not re.search(r"^\s*1\)", answer.explanation, re.MULTILINE):
            errors.append("Блок 2 не содержит нумерованных разделов (ожидается «1)»)")

        return len(errors) == 0, errors

    def _check_citation_completeness(
        self, answer: LegalAnswer
    ) -> tuple[list[str], list[str]]:
        """
        Прямая проверка: все НПА из brief+explanation имеют цитату.
        Обратная проверка: все цитаты упомянуты в тексте.
        """
        text = answer.brief + "\n" + answer.explanation
        mentioned = {m.group().strip() for m in _NPA_PATTERN.finditer(text)}
        cited_titles_lower = {c.title.lower() for c in answer.citations}

        # НПА упомянуты, но цитат нет (регистронезависимо)
        missing = [
            ref for ref in mentioned
            if not any(ref.lower() in t for t in cited_titles_lower)
        ]

        # Цитаты есть, но в тексте не упоминаются
        orphans = [
            c.title
            for c in answer.citations
            if not any(word in text for word in c.title.split() if len(word) > 3)
        ]

        return missing, orphans

    def _check_arithmetic(self, answer: LegalAnswer) -> tuple[bool, list[str]]:
        """
        Извлекает выражения вида «X × Y = Z» или «X * Y = Z» из explanation,
        пересчитывает и сравнивает с указанным результатом.
        """
        pattern = re.compile(
            r"([\d\s]+(?:[.,]\d+)?)\s*[×*x]\s*([\d\s]+(?:[.,]\d+)?)\s*%?\s*=\s*([\d\s]+(?:[.,]\d+)?)"
        )
        errors: list[str] = []

        for match in pattern.finditer(answer.explanation):
            try:
                a = float(match.group(1).replace(" ", "").replace(",", "."))
                b = float(match.group(2).replace(" ", "").replace(",", "."))
                c = float(match.group(3).replace(" ", "").replace(",", "."))
                expected = round(a * b / 100 if "%" in match.group(0) else a * b, 2)
                if abs(expected - c) > 1:  # допуск 1 единица (округление)
                    errors.append(
                        f"{match.group(0).strip()}: ожидается {expected}, указано {c}"
                    )
            except ValueError:
                pass

        return len(errors) == 0, errors

    # ------------------------------------------------------------------
    # Шаг Б: LLM-верификация
    # ------------------------------------------------------------------

    async def _llm_verify(self, answer: LegalAnswer) -> LLMVerificationResult:
        citations_json = json.dumps(
            [c.model_dump(exclude={"status", "actual_text", "source_url"}) for c in answer.citations],
            ensure_ascii=False,
            indent=2,
        )
        user_message = (
            f"Проверь актуальность следующих цитат НПА:\n\n"
            f"Краткий ответ:\n{answer.brief}\n\n"
            f"Пояснение:\n{answer.explanation}\n\n"
            f"Цитаты для проверки:\n{citations_json}"
        )

        response = await self._client.responses.create(
            model=config.MODEL,
            instructions=_VERIFIER_PROMPT,
            input=user_message,
            tools=[{"type": "web_search_preview"}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "LLMVerificationResult",
                    "schema": _VERIFIER_SCHEMA,
                    "strict": True,
                }
            },
        )

        data = json.loads(response.output_text)

        citations_results = [
            Citation(
                id=c["id"],
                title=c["title"],
                text=c["text"],
                status=CitationStatus(c["status"]),
                actual_text=c.get("actual_text"),
                source_url=c.get("source_url"),
            )
            for c in data["citations_results"]
        ]
        correction_diffs = [CorrectionDiff(**d) for d in data.get("correction_diffs", [])]

        return LLMVerificationResult(
            citations_results=citations_results,
            correction_diffs=correction_diffs,
            summary=data["summary"],
        )
