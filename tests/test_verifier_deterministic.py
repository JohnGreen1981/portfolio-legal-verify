from legal_verify.models import Citation, LegalAnswer
from legal_verify.verifier import Verifier


def _verifier() -> Verifier:
    return object.__new__(Verifier)


def test_structure_requires_three_blocks():
    answer = LegalAnswer(
        question="Тестовый вопрос",
        brief="Краткий ответ",
        explanation="Без нумерации",
        citations=[],
    )

    ok, errors = _verifier()._check_structure(answer)

    assert not ok
    assert "Блок 3" in " ".join(errors)
    assert "1)" in " ".join(errors)


def test_citation_completeness_detects_missing_reference():
    answer = LegalAnswer(
        question="Тестовый вопрос",
        brief="См. ст. 15 ТК РФ.",
        explanation="1) Дополнительно применима ч. 2 ст. 15 ТК РФ.",
        citations=[
            Citation(id=1, title="ст. 15 ТК РФ", text="Тестовая цитата"),
        ],
    )

    missing, _orphans = _verifier()._check_citation_completeness(answer)

    assert "ч. 2 ст. 15 ТК РФ" in missing


def test_arithmetic_check_detects_wrong_result():
    answer = LegalAnswer(
        question="Тестовый вопрос",
        brief="Краткий ответ",
        explanation="1) Расчет: 1000 x 20% = 300.",
        citations=[Citation(id=1, title="ст. 1 ТК РФ", text="Тестовая цитата")],
    )

    ok, errors = _verifier()._check_arithmetic(answer)

    assert not ok
    assert errors
