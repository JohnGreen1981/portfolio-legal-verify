# Legal Verify

## Назначение

Репозиторий CLI/Telegram-инструмента для генерации и проверки юридических ответов по российскому праву.

Проект показывает domain-specific AI workflow: генератор готовит ответ с цитатами НПА, верификатор проверяет структуру, полноту цитат, арифметику и актуальность норм, затем orchestration loop выбирает точечный patch или полную регенерацию.

## Стек

- Python 3.11+
- uv
- OpenAI Responses API
- Typer CLI
- Pydantic
- Rich
- python-telegram-bot

## Структура

```text
src/legal_verify/
  main.py             CLI: ask, verify, chat, bot
  bot.py              Telegram wrapper
  generator.py        генератор юридического ответа
  verifier.py         deterministic checks + LLM verification
  orchestrator.py     цикл generate -> verify -> patch/regenerate
  models.py           Pydantic-модели
  config.py           env/config
  prompts/            prompts генератора и верификатора
pyproject.toml        пакет и зависимости
uv.lock               lockfile
.env.example          безопасный шаблон окружения
```

## Роль проекта

Проект показывает AI-assisted domain verification prototype: постановке юридического workflow, prompt design, structured outputs, проверке цитат и risk control для legal AI.

Не описывать проект как замену юриста или production legaltech-систему. Это прототип workflow, где юридические выводы требуют профессиональной проверки.

## Данные

В репозитории не хранить реальные `.env`, локальная история запросов `history/`, юридические материалы клиентов, PDF-паспорта и приватные документы.

`history/` создается локально при запуске и игнорируется git.

## Правила

- Не коммитить `.env`, OpenAI ключи, Telegram token, реальные юридические вопросы, клиентские материалы и локальную историю.
- `.env.example` должен содержать только placeholder-значения.
- При изменении Python-кода запускать `python3 -m py_compile src/legal_verify/*.py`.
- Проверять изменения на отсутствие секретов.
- `AGENTS.md` и `CLAUDE.md` должны оставаться синхронизированными по смыслу.
