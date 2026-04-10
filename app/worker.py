"""ARQ worker entry point. Run with: arq app.worker.WorkerSettings"""

from app.redis import get_arq_redis_settings
from app.tasks import apply_feedback_task, generate_lessons_task, generate_overview_task


class WorkerSettings:
    functions = [
        generate_overview_task,
        apply_feedback_task,
        generate_lessons_task,
    ]
    redis_settings = get_arq_redis_settings()
    max_jobs = 4
    job_timeout = 600
    allow_abort_jobs = True
