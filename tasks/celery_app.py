from __future__ import annotations

from celery import Celery

import config

celery_app = Celery(
	"car_rag_agent",
	broker=config.CELERY_BROKER_URL,
	backend=config.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
	task_serializer="json",
	result_serializer="json",
	accept_content=["json"],
	timezone="Asia/Shanghai",
	enable_utc=False,
	task_track_started=True,
	worker_prefetch_multiplier=1,
	task_acks_late=True,
)

celery_app.autodiscover_tasks(["tasks"])
