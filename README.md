# Legal Verify

CLI/Telegram-инструмент для генерации и проверки юридических ответов по российскому праву.

Это очищенная портфельная версия. В репозитории нет production `.env`, локальной истории запросов, клиентских материалов, PDF-паспортов и приватных документов.

## Что показывает проект

- Domain-specific AI workflow для юридических ответов.
- Архитектуру generator + verifier.
- Structured outputs для ответа, цитат и отчета проверки.
- Итерационный цикл: generate -> verify -> patch или regenerate.
- Гибридную проверку: deterministic checks + LLM verification с web search.
- Risk control для legal AI: структура, полнота цитат, арифметика, актуальность норм.
- AI-assisted development: постановка юридического workflow, промпты, схемы данных, CLI/Telegram wrapper, ручная проверка и очистка для публикации.

## Пользовательский сценарий

1. Пользователь задает юридический вопрос через CLI или Telegram.
2. Генератор формирует ответ из трех блоков: краткий ответ, пояснение, цитаты НПА.
3. Верификатор проверяет структуру, полноту ссылок, арифметику и актуальность цитат.
4. Если ошибки локальные, orchestration loop запускает patch-режим.
5. Если ошибки каскадные, ответ регенерируется с учетом отчета верификации.
6. Финальный ответ сохраняется локально в `history/`.

## Стек

- Python 3.11+
- uv
- OpenAI Responses API
- Typer CLI
- Pydantic
- Rich
- python-telegram-bot

## Запуск

```bash
uv sync
cp .env.example .env
uv run legal-verify ask "Можно ли вернуть товар надлежащего качества?"
```

Нужные переменные окружения:

```env
OPENAI_API_KEY=your_openai_api_key
MODEL=gpt-5.4
MAX_ITERATIONS=3
PATCH_MAX_MISMATCHES=2
TELEGRAM_TOKEN=
```

Telegram-режим:

```bash
uv run legal-verify bot
```

## Проверка

```bash
uv run pytest
```

Тесты в clean repo проверяют детерминированную часть верификатора без OpenAI API: структуру ответа, полноту цитат и арифметику.

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
```

## Безопасность и ограничения

- Не коммитить `.env`, OpenAI ключи, Telegram token, клиентские документы и локальную историю `history/`.
- Юридические ответы требуют профессиональной проверки. Проект показывает workflow верификации, а не заменяет юриста.
- Актуальность норм зависит от качества web search и источников. Для практического использования нужен дополнительный ручной контроль.
- `history/` создается локально и игнорируется git.

## Портфельная рамка

Проект представлен как AI-assisted domain verification prototype. Фокус: проектирование legal workflow, prompt design, structured outputs, итерационная проверка цитат и контроль рисков, а не заявление о production legaltech-системе.
