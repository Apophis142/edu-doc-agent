# edu-doc-agent

![CI](https://github.com/Apophis142/edu-doc-agent/actions/workflows/ci.yml/badge.svg)

Агентная ИИ-система интеллектуального анализа, автоматизированного формирования
и проверки учебно-методических документов образовательной программы.

Система анализирует пакет документов ОП (РПД, учебный план, характеристика программы,
наборы компетенций), связывает компетенции с дисциплинами и оценочными средствами,
проверяет соответствие ФГОС ВО и профстандартам, формирует консолидированный пакет
и протокол проверки с рекомендациями.

**Заказчик:** ОЦАД СПбГУ
**Кураторы:** Коваленко Лев, Севрюков С.Ю., И.С. Блеканов

## Быстрый старт

```bash
git clone https://github.com/Apophis142/edu-doc-agent.git
cd edu-doc-agent

# 1. Зависимости
uv sync
uv run pre-commit install

# 2. Окружение
cp .env.example .env       # заполнить LLM_API_KEY, DATA_DIR
# Убедитесь, что для локального запуска REDIS_URL=redis://127.0.0.1:6379/0
# (при запуске полностью в Docker используется redis://redis:6379/0)

# 3. Инфраструктура (БД и Redis в Docker)
docker compose up -d db redis

# 4. API, Воркер и UI локально (запускать в разных окнах терминала)
make run-api     # API: http://localhost:8000/docs
make run-worker  # Фоновый воркер ARQ для обработки задач
make run-ui      # UI: http://localhost:8501
```
Полностью в Docker (как будет на демо):
```bash
docker compose up --build
```

## Команды
См. `make help`. Основное: `make test`, `make lint`, `make fmt`, `make up-db`, `make run-api`, `make run-ui`, `make up`.


## Структура репозитория

```
src/edu_doc_agent/   основной код (api, orchestration, parsing, extraction, …)
ui/                  Streamlit-интерфейс
rules/               YAML-каталог правил проверки
prompts/             промпты как файлы
docs/                документация → GitHub Pages
tests/               unit, integration, fixtures (только синтетика)
notebooks/           исследования (nbstripout вычищает выводы)
data/                реальные документы — вне git
```

## Команда

| Роль | Имя | Контакты |
| --- | --- | --- |
| PM, тестировщик | Грязнов Эдуард | @apophis142 |
| Data Science | Подтуров Павел | @clerdmy |
| Data Science | Измайлов Никита | @sskkyyrreexx |
| Data Science | | |
| Backend | Епишкин Роман | @oxxytentacion |

## Документация

- [Разбор проекта](#)
- [Архитектура](#)
- [Как мы работаем](#)
- [Решения (ADR)](#)

## Лицензия

**TBD**
