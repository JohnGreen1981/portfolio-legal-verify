from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from . import config
from .models import Citation, LegalAnswer

_PROMPT_PATH = config.PROMPTS_DIR / "generator.md"
_BASE_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# JSON-схема для structured output
_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "brief": {"type": "string"},
        "explanation": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":   {"type": "integer"},
                    "title": {"type": "string"},
                    "text":  {"type": "string"},
                },
                "required": ["id", "title", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["brief", "explanation", "citations"],
    "additionalProperties": False,
}


class Generator:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=config.require_openai_api_key())

    async def generate(
        self,
        question: str,
        verification_context: dict[str, Any] | None = None,
        iteration: int = 1,
    ) -> LegalAnswer:
        user_message = self._build_user_message(
            question, verification_context, iteration
        )

        raw = await self._call_api(user_message)
        data = json.loads(raw)

        citations = [Citation(**c) for c in data["citations"]]
        return LegalAnswer(
            question=question,
            brief=data["brief"],
            explanation=data["explanation"],
            citations=citations,
            iteration=iteration,
        )

    def _build_user_message(
        self,
        question: str,
        ctx: dict[str, Any] | None,
        iteration: int,
    ) -> str:
        if ctx is None or iteration == 1:
            return question

        mode = ctx.get("mode", "regenerate")

        if mode == "patch":
            existing = ctx["existing_answer"]
            existing_json = existing.model_dump_json(indent=2, exclude={"iteration", "verified", "question"})
            diffs_json = json.dumps(
                [d.model_dump() for d in ctx["diffs"]],
                ensure_ascii=False, indent=2
            )
            actual_texts_json = json.dumps(
                ctx.get("actual_texts", {}),
                ensure_ascii=False, indent=2
            )
            return (
                f"Режим: PATCH\n\n"
                f"Вопрос: {question}\n\n"
                f"Существующий ответ:\n{existing_json}\n\n"
                f"Исправления:\n{diffs_json}\n\n"
                f"Актуальные тексты норм:\n{actual_texts_json}"
            )

        # mode == "regenerate"
        report = ctx["report"]
        actual_texts_json = json.dumps(
            ctx.get("actual_texts", {}),
            ensure_ascii=False, indent=2
        )
        missing = ctx.get("missing_citations", [])
        return (
            f"Режим: REGENERATE\n\n"
            f"Вопрос: {question}\n\n"
            f"Предыдущий ответ содержал ошибки. Отчёт верификации:\n"
            f"{report.summary}\n\n"
            f"Устаревшие/не найденные цитаты:\n"
            + "\n".join(
                f"- {c.title}: {c.status}"
                for c in report.citations_results
                if c.status and c.status.value != "confirmed"
            )
            + f"\n\nПропущенные НПА (добавь цитаты): {missing}\n\n"
            f"Актуальные тексты норм (используй их):\n{actual_texts_json}\n\n"
            f"Сгенерируй ответ заново, не повторяй ошибок."
        )

    async def _call_api(self, user_message: str) -> str:
        response = await self._client.responses.create(
            model=config.MODEL,
            instructions=_BASE_PROMPT,
            input=user_message,
            tools=[{"type": "web_search_preview"}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "LegalAnswer",
                    "schema": _ANSWER_SCHEMA,
                    "strict": True,
                }
            },
        )
        return response.output_text
