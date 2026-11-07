"""
Роутер для управления сессиями и запуска обработки.
"""

import asyncio
import logging
from typing import Annotated
from uuid import uuid4

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Path, status
from redis.exceptions import RedisError

from edu_doc_agent.api.dependencies import get_arq_pool
from edu_doc_agent.api.schemas import ProcessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post(
    "/{session_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ProcessResponse,
)
async def process_session(
    session_id: Annotated[str, Path(..., description="ID сессии пользователя")],
    redis_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> ProcessResponse:
    """
    Запускает асинхронную проверку и обработку образовательной программы.
    Не блокирует HTTP-запрос, сразу возвращает статус 'queued'.
    """
    run_id = uuid4()

    # Отправляем задачу в очередь Redis
    try:
        async with asyncio.timeout(2.0):
            job = await redis_pool.enqueue_job(
                "process_session_task",
                session_id=session_id,
                run_id=str(run_id),
                _job_id=str(run_id),
            )

    except TimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Очередь задач временно недоступна. Повторите попытку позже.",
        ) from e

    except RedisError as e:
        logger.error("Redis connection error for session %s: %s", session_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис очередей недоступен. Повторите попытку позже.",
        ) from e

    except Exception as e:
        logger.error("Failed to enqueue job for session %s: %s", session_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка при постановке задачи в очередь.",
        ) from e

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Задача для данной сессии уже находится в очереди.",
        )

    # Возвращаем ответ клиенту, не дожидаясь завершения задачи
    return ProcessResponse(run_id=run_id, session_id=session_id, status="queued")
