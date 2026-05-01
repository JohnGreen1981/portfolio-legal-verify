from __future__ import annotations

from typing import Any

from . import config
from .generator import Generator
from .models import CitationStatus, LegalAnswer, VerificationReport
from .verifier import Verifier


class Orchestrator:
    def __init__(self) -> None:
        self._generator = Generator()
        self._verifier = Verifier()

    async def process(
        self,
        question: str,
        max_iterations: int = config.MAX_ITERATIONS,
        on_progress: Any = None,  # callback(iteration, stage, message)
    ) -> tuple[LegalAnswer, list[VerificationReport]]:
        """
        Основной цикл: генерация → верификация → (patch | regenerate).

        Возвращает финальный ответ и историю отчётов верификации.
        """
        verification_context: dict | None = None
        reports: list[VerificationReport] = []

        for i in range(max_iterations):
            iteration = i + 1
            _notify(on_progress, iteration, "generate", "генерация ответа...")

            answer = await self._generator.generate(
                question=question,
                verification_context=verification_context,
                iteration=iteration,
            )

            _notify(on_progress, iteration, "verify", "верификация цитат...")

            report = await self._verifier.verify(answer)
            reports.append(report)

            _notify(on_progress, iteration, "result", _format_report_line(report))

            _apply_citation_statuses(answer, report)

            if not report.has_errors:
                answer.verified = True
                return answer, reports

            # Готовим контекст для следующей итерации
            actual_texts = {
                c.title: c.actual_text
                for c in report.citations_results
                if c.actual_text is not None
            }

            if _is_surgical(report):
                verification_context = {
                    "mode": "patch",
                    "existing_answer": answer,
                    "diffs": report.correction_diffs,
                    "actual_texts": actual_texts,
                }
                _notify(on_progress, iteration, "strategy", "→ точечные правки")
            else:
                verification_context = {
                    "mode": "regenerate",
                    "report": report,
                    "actual_texts": actual_texts,
                    "missing_citations": report.missing_citations,
                }
                _notify(on_progress, iteration, "strategy", "→ полная регенерация")

        # Лимит итераций исчерпан — возвращаем последний ответ с флагом
        answer.verified = False
        return answer, reports


def _apply_citation_statuses(answer: LegalAnswer, report: VerificationReport) -> None:
    """Переносит статусы верификации из отчёта в цитаты финального ответа."""
    status_map = {c.id: c for c in report.citations_results}
    for citation in answer.citations:
        if citation.id in status_map:
            verified = status_map[citation.id]
            citation.status = verified.status
            citation.actual_text = verified.actual_text
            citation.source_url = verified.source_url


def _is_surgical(report: VerificationReport) -> bool:
    """
    Точечные правки применимы когда ошибки локальны:
    - нет структурных ошибок
    - нет ошибок арифметики (каскадный эффект на все блоки)
    - нет пропущенных цитат (MISSING требует изменений в тексте)
    - не более PATCH_MAX_MISMATCHES устаревших цитат, и для каждой есть actual_text
    - нет NOT_FOUND (нечего патчить)
    """
    if not report.structure_ok:
        return False
    if not report.arithmetic_ok:
        return False
    if report.missing_citations:
        return False

    mismatch_with_text = sum(
        1 for c in report.citations_results
        if c.status == CitationStatus.MISMATCH and c.actual_text
    )
    has_not_found = any(
        c.status == CitationStatus.NOT_FOUND
        for c in report.citations_results
    )

    return (
        not has_not_found
        and mismatch_with_text <= config.PATCH_MAX_MISMATCHES
    )


def _format_report_line(report: VerificationReport) -> str:
    if not report.citations_results:
        return report.summary

    confirmed = sum(1 for c in report.citations_results if c.status == CitationStatus.CONFIRMED)
    mismatch  = sum(1 for c in report.citations_results if c.status == CitationStatus.MISMATCH)
    not_found = sum(1 for c in report.citations_results if c.status == CitationStatus.NOT_FOUND)
    total = len(report.citations_results)

    parts = [f"{confirmed}/{total} цитат подтверждено"]
    if mismatch:
        parts.append(f"{mismatch} устарело")
    if not_found:
        parts.append(f"{not_found} не найдено")
    if report.missing_citations:
        parts.append(f"{len(report.missing_citations)} пропущено")
    if not report.arithmetic_ok:
        parts.append("ошибки арифметики")

    return " | ".join(parts)


def _notify(callback: Any, iteration: int, stage: str, message: str) -> None:
    if callback is not None:
        callback(iteration, stage, message)
