from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _get_bool(name: str, default: bool) -> bool:
	value = os.getenv(name)
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
	value = os.getenv(name)
	if value is None:
		return default
	try:
		return int(value)
	except ValueError:
		return default


def _get_float(name: str, default: float) -> float:
	value = os.getenv(name)
	if value is None:
		return default
	try:
		return float(value)
	except ValueError:
		return default


def _get_list(name: str, default: list[str]) -> list[str]:
	value = os.getenv(name)
	if value is None or not value.strip():
		return default
	return [item.strip() for item in value.split(",") if item.strip()]


# =============================
# Qwen API 配置
# =============================
# QWEN_API_KEY: 必填；值范围：非空字符串
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
# QWEN_API_BASE_URL: 可选；默认 DashScope 兼容端点
QWEN_API_BASE_URL = os.getenv(
	"QWEN_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
# QWEN_CHAT_MODEL: 聊天模型名，示例 qwen-plus
QWEN_CHAT_MODEL = os.getenv("QWEN_CHAT_MODEL", "qwen-plus")
# QWEN_EMBEDDING_MODEL: 向量模型名，示例 text-embedding-v2
QWEN_EMBEDDING_MODEL = os.getenv("QWEN_EMBEDDING_MODEL", "text-embedding-v2")
# QWEN_RERANK_MODEL: 重排模型名，示例 gte-rerank
QWEN_RERANK_MODEL = os.getenv("QWEN_RERANK_MODEL", "gte-rerank")
# QWEN_TIMEOUT: 单次 API 超时时间（秒），建议范围 10-300
QWEN_TIMEOUT = _get_int("QWEN_TIMEOUT", 60)
# QWEN_MAX_RETRIES: API 重试次数，建议范围 0-5
QWEN_MAX_RETRIES = _get_int("QWEN_MAX_RETRIES", 2)
# MAX_CHAT_TOKENS: 会话 token 总预算，建议范围 10_000-2_000_000
MAX_CHAT_TOKENS = _get_int("MAX_CHAT_TOKENS", 200000)


# =============================
# Ingestion 配置
# =============================
# INGESTION_CHUNK_SIZE: 分块长度，建议范围 200-2000
INGESTION_CHUNK_SIZE = _get_int("INGESTION_CHUNK_SIZE", 800)
# INGESTION_CHUNK_OVERLAP: 分块重叠长度，建议范围 0-400
INGESTION_CHUNK_OVERLAP = _get_int("INGESTION_CHUNK_OVERLAP", 100)
# INGESTION_ENABLE_ENHANCE: 是否启用 Qwen 内容增强
INGESTION_ENABLE_ENHANCE = _get_bool("INGESTION_ENABLE_ENHANCE", True)


# =============================
# 向量与检索配置
# =============================
# VECTOR_COLLECTION_NAME: Chroma 集合名称
VECTOR_COLLECTION_NAME = os.getenv("VECTOR_COLLECTION_NAME", "car_knowledge")
# VECTOR_EMBED_BATCH_SIZE: embedding 批处理大小，建议范围 1-128
VECTOR_EMBED_BATCH_SIZE = _get_int("VECTOR_EMBED_BATCH_SIZE", 16)
# VECTOR_QUERY_TOP_K: 向量检索返回数量，建议范围 1-100
VECTOR_QUERY_TOP_K = _get_int("VECTOR_QUERY_TOP_K", 10)
# HYBRID_DENSE_WEIGHT + HYBRID_SPARSE_WEIGHT 建议和为 1.0
HYBRID_DENSE_WEIGHT = _get_float("HYBRID_DENSE_WEIGHT", 0.7)
HYBRID_SPARSE_WEIGHT = _get_float("HYBRID_SPARSE_WEIGHT", 0.3)
# RERANK_TOP_K: 重排后保留数量，建议范围 1-20
RERANK_TOP_K = _get_int("RERANK_TOP_K", 5)
# RERANK_SCORE_THRESHOLD: 重排分数阈值，建议范围 0.0-1.0
RERANK_SCORE_THRESHOLD = _get_float("RERANK_SCORE_THRESHOLD", 0.0)


# =============================
# 数据存储配置
# =============================
STORAGE_DIR = BASE_DIR / "storage"
RAW_DATA_DIR = STORAGE_DIR / "raw_data"
PROCESSED_DATA_DIR = STORAGE_DIR / "processed_data"
VECTOR_DB_DIR = STORAGE_DIR / "vector_db"
LOG_DIR = STORAGE_DIR / "logs"
CHAT_HISTORY_DIR = STORAGE_DIR / "chat_history"
TEMP_DIR = STORAGE_DIR / "temp"
BACKUP_DIR = STORAGE_DIR / "backup"


# =============================
# 爬虫配置
# =============================
# CRAWL_DEFAULT_PLATFORMS: 默认平台列表
CRAWL_DEFAULT_PLATFORMS = _get_list("CRAWL_DEFAULT_PLATFORMS", ["autohome"])
# CRAWL_DEFAULT_CONTENT_TYPES: 默认抓取类别（news/specs/comments）
CRAWL_DEFAULT_CONTENT_TYPES = _get_list(
	"CRAWL_DEFAULT_CONTENT_TYPES", ["news", "specs", "comments"]
)
# CRAWL_MAX_SCROLL: 资讯流最大滚动轮次，建议范围 1-50
CRAWL_MAX_SCROLL = _get_int("CRAWL_MAX_SCROLL", 3)
# CRAWL_MAX_COMMENT_PAGES: 评论最大翻页数，建议范围 1-100
CRAWL_MAX_COMMENT_PAGES = _get_int("CRAWL_MAX_COMMENT_PAGES", 3)
# CRAWL_NAV_TIMEOUT_MS: 页面导航超时（毫秒），建议范围 5000-120000
CRAWL_NAV_TIMEOUT_MS = _get_int("CRAWL_NAV_TIMEOUT_MS", 30000)
# CRAWL_RETRY_COUNT: 单页面抓取失败重试次数，建议范围 0-5
CRAWL_RETRY_COUNT = _get_int("CRAWL_RETRY_COUNT", 2)
# CRAWL_REQUEST_DELAY_SECONDS: 防爬虫延时（秒），建议范围 0.2-10
CRAWL_REQUEST_DELAY_SECONDS = _get_float("CRAWL_REQUEST_DELAY_SECONDS", 1.0)


# =============================
# Celery 配置
# =============================
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv(
	"CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1"
)


# =============================
# UI 配置
# =============================
UI_PASSWORD = os.getenv("UI_PASSWORD", "")
# UI_TASK_POLL_INTERVAL_SECONDS: 轮询间隔，建议范围 1-10
UI_TASK_POLL_INTERVAL_SECONDS = _get_int("UI_TASK_POLL_INTERVAL_SECONDS", 2)


def validate_core_config() -> dict[str, Any]:
	"""返回配置校验结果，便于启动前检查。"""
	errors: list[str] = []
	warnings: list[str] = []

	if not QWEN_API_KEY:
		warnings.append("QWEN_API_KEY 未设置，涉及大模型能力的流程将不可用。")

	if INGESTION_CHUNK_OVERLAP >= INGESTION_CHUNK_SIZE:
		errors.append("INGESTION_CHUNK_OVERLAP 必须小于 INGESTION_CHUNK_SIZE。")

	if not (0.0 <= RERANK_SCORE_THRESHOLD <= 1.0):
		errors.append("RERANK_SCORE_THRESHOLD 取值必须在 0.0 到 1.0 之间。")

	if HYBRID_DENSE_WEIGHT < 0 or HYBRID_SPARSE_WEIGHT < 0:
		errors.append("HYBRID_DENSE_WEIGHT 与 HYBRID_SPARSE_WEIGHT 必须为非负数。")

	if abs((HYBRID_DENSE_WEIGHT + HYBRID_SPARSE_WEIGHT) - 1.0) > 0.01:
		warnings.append("HYBRID_DENSE_WEIGHT + HYBRID_SPARSE_WEIGHT 建议接近 1.0。")

	return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}
