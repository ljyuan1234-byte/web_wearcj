from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

DEFAULT_ENCODING = "utf-8"

__all__ = [
	"DEFAULT_ENCODING",
	"ensure_dir",
	"clean_text",
	"get_logger",
	"classify_exception",
	"handle_exception",
	"load_prompt",
	"save_chat_history",
	"load_chat_history",
	"generate_doc_id",
	"split_text_chunks",
	"parse_webpage_with_fallback",
	"backup_vector_db",
	"restore_vector_db",
]


def ensure_dir(path: str | Path) -> Path:
	"""Create a directory when it does not exist and return Path."""
	directory = Path(path)
	directory.mkdir(parents=True, exist_ok=True)
	return directory


def clean_text(text: str) -> str:
	"""Normalize whitespaces and remove low-value control characters."""
	if not text:
		return ""

	normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
	normalized = normalized.replace("\u3000", " ")
	normalized = re.sub(r"\s+", " ", normalized)
	return normalized.strip()


def get_logger(
	name: str,
	log_dir: str | Path = "storage/logs",
	level: int = logging.INFO,
) -> logging.Logger:
	"""Build a reusable logger with stream/file handlers."""
	logger = logging.getLogger(name)
	logger.setLevel(level)

	if logger.handlers:
		return logger

	formatter = logging.Formatter(
		"%(asctime)s | %(levelname)s | %(name)s | %(message)s"
	)

	stream_handler = logging.StreamHandler()
	stream_handler.setFormatter(formatter)
	logger.addHandler(stream_handler)

	log_path = ensure_dir(log_dir) / f"{name}.log"
	file_handler = logging.FileHandler(log_path, encoding=DEFAULT_ENCODING)
	file_handler.setFormatter(formatter)
	logger.addHandler(file_handler)

	logger.propagate = False
	return logger


def classify_exception(exc: Exception) -> str:
	"""Map runtime exceptions to stable error categories."""
	if isinstance(exc, TimeoutError):
		return "timeout_error"
	if isinstance(exc, (ConnectionError, OSError)):
		return "network_error"
	if isinstance(exc, ValueError):
		return "value_error"
	if isinstance(exc, KeyError):
		return "key_error"
	return "unknown_error"


def handle_exception(
	exc: Exception,
	logger: logging.Logger | None = None,
	context: str = "",
) -> dict[str, Any]:
	"""Return normalized error info and optionally log stack traces."""
	error_payload = {
		"ok": False,
		"error_type": classify_exception(exc),
		"error_message": str(exc),
		"context": context,
	}
	if logger:
		logger.exception("%s | %s", context or "runtime_error", exc)
	return error_payload


def load_prompt(prompt_name_or_path: str, base_dir: str | Path = "prompts") -> str:
	"""Load prompt file from absolute path or the prompts directory."""
	path = Path(prompt_name_or_path)
	if not path.exists():
		path = Path(base_dir) / prompt_name_or_path

	if not path.exists():
		raise FileNotFoundError(f"Prompt file not found: {prompt_name_or_path}")

	return path.read_text(encoding=DEFAULT_ENCODING)


def save_chat_history(
	session_id: str,
	messages: list[dict[str, Any]],
	history_dir: str | Path = "storage/chat_history",
) -> Path:
	"""Persist chat history for a session in JSON format."""
	if not session_id:
		raise ValueError("session_id is required")

	target_dir = ensure_dir(history_dir)
	path = target_dir / f"{session_id}.json"
	payload = {
		"session_id": session_id,
		"updated_at": datetime.utcnow().isoformat() + "Z",
		"messages": messages,
	}
	path.write_text(
		json.dumps(payload, ensure_ascii=False, indent=2),
		encoding=DEFAULT_ENCODING,
	)
	return path


def load_chat_history(
	session_id: str,
	history_dir: str | Path = "storage/chat_history",
) -> list[dict[str, Any]]:
	"""Load chat history by session id, return empty list when absent."""
	path = Path(history_dir) / f"{session_id}.json"
	if not path.exists():
		return []

	payload = json.loads(path.read_text(encoding=DEFAULT_ENCODING))
	return payload.get("messages", [])


def generate_doc_id(source: str, content: str, extra: str = "") -> str:
	"""Generate stable document id for ingestion and deduplication."""
	fingerprint = "|".join([clean_text(source), clean_text(content), clean_text(extra)])
	return sha1(fingerprint.encode(DEFAULT_ENCODING)).hexdigest()


def split_text_chunks(
	text: str,
	chunk_size: int = 800,
	chunk_overlap: int = 100,
) -> list[str]:
	"""Split text into overlapped chunks for retrieval pipelines."""
	content = clean_text(text)
	if not content:
		return []
	if chunk_size <= 0:
		raise ValueError("chunk_size must be greater than 0")
	if chunk_overlap < 0:
		raise ValueError("chunk_overlap must be >= 0")
	if chunk_overlap >= chunk_size:
		raise ValueError("chunk_overlap must be less than chunk_size")

	chunks: list[str] = []
	step = chunk_size - chunk_overlap
	for index in range(0, len(content), step):
		piece = content[index : index + chunk_size]
		if piece:
			chunks.append(piece)
		if index + chunk_size >= len(content):
			break
	return chunks


def parse_webpage_with_fallback(
	html_content: str,
	parser_order: tuple[str, ...] = ("lxml", "html.parser"),
) -> dict[str, str]:
	"""Parse webpage text with parser fallback to improve robustness."""
	if not html_content:
		return {"title": "", "text": "", "parser": ""}

	last_error = None
	for parser in parser_order:
		try:
			soup = BeautifulSoup(html_content, parser)
			for tag in soup(["script", "style", "noscript"]):
				tag.extract()

			title = clean_text(soup.title.get_text()) if soup.title else ""
			text = clean_text(soup.get_text(separator=" "))
			return {"title": title, "text": text, "parser": parser}
		except Exception as exc:  # noqa: BLE001
			last_error = exc

	raise RuntimeError(f"Failed to parse webpage: {last_error}")


def backup_vector_db(
	vector_db_dir: str | Path = "storage/vector_db",
	backup_root: str | Path = "storage/backup",
) -> Path:
	"""Create timestamped backup for vector database directory."""
	src = Path(vector_db_dir)
	if not src.exists():
		raise FileNotFoundError(f"Vector DB directory does not exist: {src}")

	backup_dir = ensure_dir(backup_root)
	target = backup_dir / f"vector_db_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
	shutil.copytree(src, target)
	return target


def restore_vector_db(
	backup_path: str | Path,
	vector_db_dir: str | Path = "storage/vector_db",
) -> Path:
	"""Restore vector database from backup directory."""
	src = Path(backup_path)
	if not src.exists():
		raise FileNotFoundError(f"Backup path does not exist: {src}")

	target = Path(vector_db_dir)
	if target.exists():
		shutil.rmtree(target)
	shutil.copytree(src, target)
	return target
