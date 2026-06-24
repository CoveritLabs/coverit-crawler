from __future__ import annotations

from arq.worker import run_worker

from src import config
from src.workers.jobs.flow_editor_session import flow_editor_session
from src.workers.jobs.manual_record_session import manual_record_session
from src.workers.main import (
    _redis_settings_from_url,
    arq_job_deserializer,
    arq_job_serializer,
    shutdown,
    startup,
)


class ManualWorkerSettings:
    redis_settings = _redis_settings_from_url(config.REDIS_URL or "redis://localhost:6379/0")
    queue_name = config.MANUAL_ARQ_QUEUE_NAME
    functions = [manual_record_session, flow_editor_session]
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = []
    max_jobs = config.MANUAL_CRAWLER_MAX_JOBS
    job_timeout = config.MANUAL_CRAWLER_JOB_TIMEOUT_SECONDS
    keep_result = 0
    allow_abort_jobs = True
    job_serializer = arq_job_serializer
    job_deserializer = arq_job_deserializer
    expires_extra_ms = config.ARQ_JOB_EXPIRES_MS


if __name__ == "__main__":
    run_worker(ManualWorkerSettings)
