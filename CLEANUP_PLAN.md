# План очистки

- [x] Перенести только `src/legal_verify/`, `pyproject.toml`, `uv.lock` и публичные docs.
- [x] Исключить `.env`, `.venv`, `history/`, кэши, локальные PDF и приватные заметки.
- [x] Создать безопасный `.env.example`.
- [x] Добавить публичные `AGENTS.md` / `CLAUDE.md`.
- [x] Переписать README/SECURITY/CLEANUP на русский.
- [x] Добавить тесты или demo fixtures без реальных юридических вопросов.
- [x] Запустить tests/syntax check (`3 passed`; `python3 -m py_compile` пройден).
- [x] Запустить проверку на секреты перед первой публикацией в GitHub.
