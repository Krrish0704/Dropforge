import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "dropforge_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Route new reservations to the default queue automatically
    task_routes={
        "process_payment": {"queue": "default"},
    }
)

celery_app.conf.beat_schedule = {
    "reap-expired-turns": {
        "task": "advance_all_expired_turns",
        "schedule": 2.0, 
    },
}