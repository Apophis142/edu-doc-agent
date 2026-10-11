"""Общие фикстуры и настройки pytest для всего проекта."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from edu_doc_agent.main import app


def pytest_addoption(parser: pytest.Parser) -> None:
    """Регистрирует кастомные флаги командной строки.

    По умолчанию тесты, которым нужна настоящая LLM или БД,
    пропускаются: они медленные, дорогие и/или требуют
    окружения, которого нет в CI.
    """
    parser.addoption(
        "--run-llm",
        action="store_true",
        default=False,
        help="Запустить тесты, которые ходят в настоящую LLM.",
    )
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Запустить интеграционные тесты (нужна БД).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Снимает skip с тестов по флагам --run-llm и --run-integration."""
    if not config.getoption("--run-llm"):
        skip_llm = pytest.mark.skip(reason="нужен флаг --run-llm")
        for item in items:
            if "llm" in item.keywords:
                item.add_marker(skip_llm)

    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(reason="нужен флаг --run-integration")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


@pytest.fixture
def client() -> Iterator[TestClient]:
    """HTTP-клиент к FastAPI-приложению для юнит-тестов API."""
    with TestClient(app) as test_client:
        yield test_client
