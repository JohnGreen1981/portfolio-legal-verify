from __future__ import annotations

import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from . import config
from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Максимальная длина сообщения Telegram
_TG_LIMIT = 4096


def _escape(text: str) -> str:
    """Экранирует спецсимволы для MarkdownV2."""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


async def _send_long(update: Update, text: str, parse_mode: str | None = None) -> None:
    """Разбивает длинное сообщение на части по _TG_LIMIT символов."""
    for i in range(0, len(text), _TG_LIMIT):
        chunk = text[i : i + _TG_LIMIT]
        await update.message.reply_text(chunk, parse_mode=parse_mode)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 LegalVerify — юридический ассистент.\n\n"
        "Задайте вопрос по российскому праву, и я отвечу с верифицированными цитатами НПА.\n\n"
        "/help — справка"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Просто напишите юридический вопрос — я отвечу.\n\n"
        "Ответ состоит из трёх частей:\n"
        "• Краткий ответ\n"
        "• Пояснение с аргументацией\n"
        "• Цитаты НПА (верифицированы через web-поиск)\n\n"
        "Верификация занимает 30–90 секунд."
    )


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text.strip()
    if not question:
        return

    # Сообщение-заглушка с прогрессом
    progress_msg = await update.message.reply_text("⏳ Итерация 1 → генерация ответа...")

    orchestrator = Orchestrator()
    last_stage = ""

    def on_progress(iteration: int, stage: str, message: str) -> None:
        nonlocal last_stage
        last_stage = f"⏳ Итерация {iteration} → {message}"
        # Редактируем сообщение прогресса (fire-and-forget через create_task)
        context.application.create_task(
            progress_msg.edit_text(last_stage),
            update=update,
        )

    try:
        answer, reports = await orchestrator.process(
            question=question,
            on_progress=on_progress,
        )
    except Exception as e:
        logger.exception("Ошибка при обработке вопроса")
        await progress_msg.edit_text(f"❌ Ошибка: {e}")
        return

    # Статус
    if answer.verified:
        iters = answer.iteration
        status = f"✅ Верифицирован ({iters} {'итерация' if iters == 1 else 'итерации' if iters <= 4 else 'итераций'})"
    else:
        status = "⚠️ Не все цитаты подтверждены"

    await progress_msg.edit_text(status)

    # Блок 1: Краткий ответ
    brief_text = f"*Краткий ответ*\n\n{answer.brief}"
    await _send_long(update, brief_text)

    # Блок 2: Пояснение
    explanation_text = f"*Пояснение*\n\n{answer.explanation}"
    await _send_long(update, explanation_text)

    # Блок 3: Цитаты — каждая отдельным сообщением если длинные, иначе всё вместе
    citations_lines = ["*Нормативно\\-правовые акты и цитаты*"]
    for c in answer.citations:
        if c.status and c.status.value == "confirmed":
            icon = "✅"
        elif c.status and c.status.value == "mismatch":
            icon = "❌"
        elif c.status and c.status.value == "not_found":
            icon = "⚠️"
        else:
            icon = "○"

        block = f"\n{icon} *{_escape(c.title)}*\n{_escape(c.text)}"
        citations_lines.append(block)

    citations_text = "\n".join(citations_lines)
    await _send_long(update, citations_text, parse_mode=ParseMode.MARKDOWN_V2)

    # Сохраняем в history
    _save(answer, reports)


def _save(answer, reports) -> None:
    import json
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.HISTORY_DIR / f"tg_{ts}.json"
    data = {
        "answer": answer.model_dump(),
        "reports": [r.model_dump() for r in reports],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    return app


def run(token: str) -> None:
    app = build_app(token)
    logger.info("Бот запущен")
    app.run_polling(drop_pending_updates=True)
