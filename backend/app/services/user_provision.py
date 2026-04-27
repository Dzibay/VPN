"""Генерация идентификаторов пользователя VPN и постановка синхронизации Xray в очередь."""

from __future__ import annotations

import logging
import uuid as uuid_lib
from secrets import token_urlsafe

from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus

from app.core.config import settings
from app.core.queue import get_install_queue, get_redis

log = logging.getLogger("app.user_provision")

_SUBSCRIPTION_TOKEN_BYTES = 24

RQ_JOB_ID_SYNC_XRAY_ALL = "vpn:sync_xray_clients:all"

_ACTIVE_XRAY_SYNC_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.CREATED,
        JobStatus.QUEUED,
        JobStatus.STARTED,
        JobStatus.SCHEDULED,
        JobStatus.DEFERRED,
    }
)

_TERMINAL_XRAY_SYNC_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.FINISHED,
        JobStatus.FAILED,
        JobStatus.STOPPED,
        JobStatus.CANCELED,
    }
)


def new_subscription_token() -> str:
    return token_urlsafe(_SUBSCRIPTION_TOKEN_BYTES)


def new_vless_uuid() -> str:
    return str(uuid_lib.uuid4())


def _rq_job_id_sync_xray_server(server_id: int) -> str:
    return f"vpn:sync_xray_clients:server:{int(server_id)}"


def _coalesce_enqueue(
    *,
    job_id: str,
    func_path: str,
    job_timeout: int,
    job_args: tuple[object, ...] = (),
) -> str:
    """
    Одна активная задача на стабильный job_id: не плодим дубликаты в RQ при наплыве запросов.

    Завершённые / упавшие задачи удаляются и можно поставить новую с тем же id.
    """
    conn = get_redis()
    q = get_install_queue()
    try:
        job = Job.fetch(job_id, connection=conn)
        st = job.get_status()
        if st in _ACTIVE_XRAY_SYNC_STATUSES:
            log.debug(
                "xray sync coalesce: пропуск, job_id=%s уже %s",
                job_id,
                st,
            )
            return job_id
        if st in _TERMINAL_XRAY_SYNC_STATUSES:
            job.delete()
        else:
            log.warning(
                "xray sync coalesce: неожиданный статус job_id=%s (%s), пересоздаём",
                job_id,
                st,
            )
            job.delete()
    except NoSuchJobError:
        pass

    q.enqueue(
        func_path,
        *job_args,
        job_id=job_id,
        job_timeout=job_timeout,
    )
    return job_id


def ensure_sync_xray_clients_all_servers_enqueued() -> str:
    """
    Полный sync inbound на всех provision_ready узлах.
    Идемпотентно относительно очереди: повторные вызовы не создают вторую активную задачу.
    """
    return _coalesce_enqueue(
        job_id=RQ_JOB_ID_SYNC_XRAY_ALL,
        func_path="worker.jobs.sync_xray_clients_all_servers",
        job_timeout=max(settings.provision_job_timeout, 600),
    )


def ensure_sync_xray_clients_to_server_enqueued(server_id: int) -> str:
    """Точечный sync на одном узле (каскад, ручной вызов API)."""
    sid = int(server_id)
    return _coalesce_enqueue(
        job_id=_rq_job_id_sync_xray_server(sid),
        func_path="worker.jobs.sync_xray_clients_to_server",
        job_timeout=max(settings.provision_subprocess_timeout, 300),
        job_args=(sid,),
    )


def enqueue_sync_xray_clients_all_servers() -> None:
    """Для BackgroundTasks: ошибки Redis только в лог (как раньше)."""
    try:
        ensure_sync_xray_clients_all_servers_enqueued()
    except RedisError:
        log.warning(
            "Не удалось поставить в очередь синхронизацию Xray (Redis недоступен)",
            exc_info=True,
        )


def enqueue_sync_xray_clients_to_server(server_id: int) -> None:
    """Для каскада / внутренних вызовов: не бросает RedisError наружу."""
    try:
        ensure_sync_xray_clients_to_server_enqueued(server_id)
    except RedisError:
        log.warning(
            "Не удалось поставить в очередь sync Xray для server_id=%s (Redis)",
            server_id,
            exc_info=True,
        )
