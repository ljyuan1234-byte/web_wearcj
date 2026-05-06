from __future__ import annotations

from typing import Any

from celery import states
from celery.exceptions import Ignore

import config
from core import get_logger, handle_exception
from skills.ingestion_skill import IngestionSkill
from skills.rag_vector_skill import RagVectorSkill
from skills.web_crawl_skill import WebCrawlSkill
from tasks.celery_app import celery_app

logger = get_logger("crawl_tasks")


@celery_app.task(bind=True, name="tasks.crawl_tasks.crawl_and_process")
def crawl_and_process(
	self,
	platform: str,
	content_types: list[str] | None = None,
	query: str | None = None,
	options: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""异步执行爬取->清洗处理->向量入库全链路。

	注意：该任务用于 UI 异步提交，避免页面阻塞。
	"""
	options = options or {}
	selected_content_types = content_types or config.CRAWL_DEFAULT_CONTENT_TYPES

	try:
		self.update_state(
			state="PROGRESS",
			meta={"step": "crawl", "message": "开始执行网页爬取"},
		)
		crawl_skill = WebCrawlSkill(raw_root=config.RAW_DATA_DIR)
		crawl_result = crawl_skill.run(
			{
				"platform": platform,
				"content_types": selected_content_types,
				"query": query or "",
				"max_scroll": int(options.get("max_scroll", config.CRAWL_MAX_SCROLL)),
				"max_pages": int(
					options.get("max_pages", config.CRAWL_MAX_COMMENT_PAGES)
				),
			}
		)
		if crawl_result.get("status") != "success":
			raise RuntimeError(f"crawl stage failed: {crawl_result.get('message')}")

		raw_data_list = crawl_result.get("data", {}).get("items", [])

		self.update_state(
			state="PROGRESS",
			meta={"step": "ingestion", "message": "开始执行数据清洗与分块"},
		)
		ingestion_skill = IngestionSkill(processed_dir=config.PROCESSED_DATA_DIR)
		ingestion_result = ingestion_skill.run(
			{
				"raw_data_list": raw_data_list,
				"enable_enhance": bool(
					options.get("enable_enhance", config.INGESTION_ENABLE_ENHANCE)
				),
				"chunk_size": int(options.get("chunk_size", config.INGESTION_CHUNK_SIZE)),
				"chunk_overlap": int(
					options.get("chunk_overlap", config.INGESTION_CHUNK_OVERLAP)
				),
			}
		)
		if ingestion_result.get("status") != "success":
			raise RuntimeError(
				f"ingestion stage failed: {ingestion_result.get('message')}"
			)

		processed_data_list = ingestion_result.get("data", {}).get(
			"processed_data_list", []
		)

		self.update_state(
			state="PROGRESS",
			meta={"step": "vector", "message": "开始执行向量化与入库"},
		)
		vector_skill = RagVectorSkill(
			vector_db_dir=config.VECTOR_DB_DIR,
			collection_name=config.VECTOR_COLLECTION_NAME,
		)
		vector_result = vector_skill.run(
			{
				"processed_data_list": processed_data_list,
				"collection_name": str(
					options.get("collection_name", config.VECTOR_COLLECTION_NAME)
				),
				"batch_size": int(
					options.get("batch_size", config.VECTOR_EMBED_BATCH_SIZE)
				),
				"backup_after_insert": bool(options.get("backup_after_insert", True)),
			}
		)
		if vector_result.get("status") != "success":
			raise RuntimeError(f"vector stage failed: {vector_result.get('message')}")

		return {
			"status": "success",
			"data": {
				"task_id": self.request.id,
				"platform": platform,
				"content_types": selected_content_types,
				"crawl": crawl_result.get("data", {}),
				"ingestion": ingestion_result.get("data", {}),
				"vector": vector_result.get("data", {}),
			},
			"message": "crawl->ingestion->vector pipeline completed",
		}
	except Exception as exc:  # noqa: BLE001
		error = handle_exception(exc, logger=logger, context="crawl_and_process")
		self.update_state(state=states.FAILURE, meta=error)
		raise Ignore()
