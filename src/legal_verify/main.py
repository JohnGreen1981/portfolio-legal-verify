from __future__ import annotations

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import config
from .models import CitationStatus, LegalAnswer, VerificationReport
from .orchestrator import Orchestrator

app = typer.Typer(
    name="legal-verify",
    help="Юридический ассистент с верификацией цитат НПА.",
    add_completion=False,
)
console = Console()


# ---------------------------------------------------------------------------
# Команда: ask
# ---------------------------------------------------------------------------

@app.command()
def ask(
    question: str = typer.Argument(..., help="Юридический вопрос"),
    max_iterations: int = typer.Option(
        config.MAX_ITERATIONS, "--max-iterations", "-n",
        help="Максимальное число итераций верификации"
    ),
    save: bool = typer.Option(True, help="Сохранить ответ в history/"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Показывать детали верификации"),
) -> None:
    """Задать юридический вопрос и получить верифицированный ответ."""
    asyncio.run(_ask(question, max_iterations, save, verbose))


async def _ask(
    question: str,
    max_iterations: int,
    save: bool,
    verbose: bool,
) -> None:
    orchestrator = Orchestrator()
    spinner_text = ""

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Запуск...", total=None)

        def on_progress(iteration: int, stage: str, message: str) -> None:
            nonlocal spinner_text
            spinner_text = f"Итерация {iteration} → {message}"
            progress.update(task, description=spinner_text)
            if verbose and stage in ("result", "strategy"):
                console.print(f"  [dim]Итерация {iteration}: {message}[/dim]")

        answer, reports = await orchestrator.process(
            question=question,
            max_iterations=max_iterations,
            on_progress=on_progress,
        )

    _print_answer(answer, reports, verbose)

    if save:
        _save_answer(answer, reports)


def _print_answer(
    answer: LegalAnswer,
    reports: list[VerificationReport],
    verbose: bool,
) -> None:
    # Статус верификации
    if answer.verified:
        iterations = answer.iteration
        status = f"[green]✅ Верифицирован ({iterations} {_iter_word(iterations)})[/green]"
    else:
        status = "[yellow]⚠️  Не все цитаты подтверждены[/yellow]"

    console.print(Panel(status, expand=False))
    console.print()

    # Блок 1
    console.print("[bold]## Краткий ответ[/bold]")
    console.print(Markdown(answer.brief))
    console.print()

    # Блок 2
    console.print("[bold]## Пояснение[/bold]")
    console.print(Markdown(answer.explanation))
    console.print()

    # Блок 3
    console.print("[bold]## Нормативно-правовые акты и цитаты[/bold]")
    for c in answer.citations:
        status_icon = _citation_icon(c.status)
        console.print(f"\n[bold]{status_icon} {c.title}[/bold]")
        console.print(c.text)

    # Детали верификации (если verbose или есть ошибки)
    if verbose or not answer.verified:
        _print_verification_details(reports)


def _print_verification_details(reports: list[VerificationReport]) -> None:
    if not reports:
        return

    console.print()
    console.print("[bold dim]── Детали верификации ──[/bold dim]")

    for i, report in enumerate(reports, 1):
        table = Table(title=f"Итерация {i}", show_header=True, header_style="bold")
        table.add_column("Цитата", style="dim", width=35)
        table.add_column("Статус", width=12)
        table.add_column("Примечание")

        for c in report.citations_results:
            icon = _citation_icon(c.status)
            note = ""
            if c.status == CitationStatus.MISMATCH and c.actual_text:
                note = "Текст обновлён"
            elif c.status == CitationStatus.NOT_FOUND:
                note = "Не удалось найти в источниках"
            table.add_row(c.title, f"{icon} {c.status.value if c.status else '—'}", note)

        console.print(table)

        if report.structure_errors:
            console.print(f"  [red]Структурные ошибки:[/red] {', '.join(report.structure_errors)}")
        if report.arithmetic_errors:
            console.print(f"  [red]Ошибки арифметики:[/red] {', '.join(report.arithmetic_errors)}")
        if report.missing_citations:
            console.print(f"  [yellow]Пропущены цитаты:[/yellow] {', '.join(report.missing_citations)}")


def _save_answer(answer: LegalAnswer, reports: list[VerificationReport]) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.HISTORY_DIR / f"{ts}.json"
    data = {
        "answer": answer.model_dump(),
        "reports": [r.model_dump() for r in reports],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"\n[dim]Сохранено: {path}[/dim]")


# ---------------------------------------------------------------------------
# Команда: bot
# ---------------------------------------------------------------------------

@app.command()
def bot(
    token: str = typer.Option(
        None, "--token", envvar="TELEGRAM_TOKEN",
        help="Telegram bot token (или TELEGRAM_TOKEN в .env)"
    ),
) -> None:
    """Запустить Telegram-бота."""
    import logging
    from .bot import run as bot_run

    logging.basicConfig(level=logging.INFO)

    t = token or config.TELEGRAM_TOKEN
    if not t:
        console.print("[red]Не указан TELEGRAM_TOKEN — добавьте в .env или передайте --token[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Бот запущен. Нажмите Ctrl+C для остановки.[/green]")
    bot_run(t)


# ---------------------------------------------------------------------------
# Команда: verify
# ---------------------------------------------------------------------------

@app.command()
def verify(
    file: Path = typer.Argument(..., help="JSON-файл с ответом (из history/)"),
) -> None:
    """Верифицировать готовый ответ из файла."""
    asyncio.run(_verify_file(file))


async def _verify_file(file: Path) -> None:
    from .verifier import Verifier

    raw = json.loads(file.read_text(encoding="utf-8"))

    # Поддерживаем как чистый LegalAnswer, так и обёртку из history/
    if "answer" in raw:
        answer_data = raw["answer"]
    else:
        answer_data = raw

    answer = LegalAnswer(**answer_data)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Верификация цитат...", total=None)
        verifier = Verifier()
        report = await verifier.verify(answer)

    _print_verification_details([report])

    if report.has_errors:
        console.print(f"\n[yellow]⚠️  {report.summary}[/yellow]")
    else:
        console.print(f"\n[green]✅ {report.summary}[/green]")


# ---------------------------------------------------------------------------
# Команда: chat
# ---------------------------------------------------------------------------

@app.command()
def chat(
    max_iterations: int = typer.Option(
        config.MAX_ITERATIONS, "--max-iterations", "-n",
        help="Максимальное число итераций верификации"
    ),
    save: bool = typer.Option(True, help="Сохранять ответы в history/"),
) -> None:
    """Интерактивный режим — задавай вопросы один за другим."""
    asyncio.run(_chat(max_iterations, save))


async def _chat(max_iterations: int, save: bool) -> None:
    session: list[str] = []  # вопросы текущей сессии

    console.print(Panel(
        "[bold]LegalVerify — интерактивный режим[/bold]\n"
        "[dim]/exit — выйти  |  /history — список вопросов сессии[/dim]",
        expand=False,
    ))
    console.print()

    while True:
        try:
            question = console.input("[bold cyan]Вопрос:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Выход.[/dim]")
            break

        if not question:
            continue

        if question.lower() in ("/exit", "/quit", "exit", "quit"):
            console.print("[dim]Выход.[/dim]")
            break

        if question.lower() == "/history":
            if not session:
                console.print("[dim]Вопросов в сессии пока нет.[/dim]\n")
            else:
                for i, q in enumerate(session, 1):
                    console.print(f"  [dim]{i}. {q}[/dim]")
                console.print()
            continue

        session.append(question)
        console.print()

        await _ask(question, max_iterations, save, verbose=False)
        console.print()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _citation_icon(status: CitationStatus | None) -> str:
    if status is None:
        return "○"
    return {
        CitationStatus.CONFIRMED:  "✅",
        CitationStatus.MISMATCH:   "❌",
        CitationStatus.NOT_FOUND:  "⚠️",
        CitationStatus.MISSING:    "➕",
    }.get(status, "○")


def _iter_word(n: int) -> str:
    if n == 1:
        return "итерация"
    if 2 <= n <= 4:
        return "итерации"
    return "итераций"


if __name__ == "__main__":
    app()
