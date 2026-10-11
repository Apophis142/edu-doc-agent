"""Точка входа FastAPI-приложения."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from edu_doc_agent import __version__

app = FastAPI(
    title="edu-doc-agent",
    description=(
        "Агентная ИИ-система интеллектуального анализа, автоматизированного "
        "формирования и проверки учебно-методических документов образовательной программы."
    ),
    version=__version__,
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Редирект на интерактивную документацию."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["service"])
def health() -> dict[str, str]:
    """Проверка живости сервиса."""
    return {"status": "ok", "version": __version__}
