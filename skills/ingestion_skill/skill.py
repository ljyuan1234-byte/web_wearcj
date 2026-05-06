from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core import (
	BaseSkill,
	QwenClient,
	clean_text,
	ensure_dir,
	generate_doc_id,
	handle_exception,
	split_text_chunks,
)


class IngestionSkill(BaseSkill):
	"""Ingestion processing skill.

	This skill provides a practical framework and key interfaces for:
	- cleaning raw text
	- chunking content
	- metadata enrichment
	- optional Qwen-based content enhancement
	"""

	name = "ingestion_skill"
	desc = "Process raw crawler data into structured chunks"

	def __init__(self, processed_dir: str | Path = "storage/processed_data") -> None:
		super().__init__()
		self.processed_dir = Path(processed_dir)
		self._qwen_client: QwenClient | None = None

	def version(self) -> str:
		return "1.0.0"

	def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
		raw_data_list = input_data.get("raw_data_list")
		if not isinstance(raw_data_list, list) or not raw_data_list:
			return {
				"status": "error",
				"data": {},
				"message": "raw_data_list is required and must be a non-empty list",
			}

		enable_enhance = bool(input_data.get("enable_enhance", True))
		chunk_size = int(input_data.get("chunk_size", 800))
		chunk_overlap = int(input_data.get("chunk_overlap", 100))

		processed_data_list: list[dict[str, Any]] = []
		failed_count = 0

		try:
			for raw_item in raw_data_list:
				try:
					chunks = self._process_single_item(
						raw_item=raw_item,
						enable_enhance=enable_enhance,
						chunk_size=chunk_size,
						chunk_overlap=chunk_overlap,
					)
					processed_data_list.extend(chunks)
				except Exception as exc:  # noqa: BLE001
					failed_count += 1
					handle_exception(exc, logger=self.logger, context="process_single_item")

			saved_path = self._save_processed_data(processed_data_list)
			return {
				"status": "success",
				"data": {
					"processed_data_list": processed_data_list,
					"count": len(processed_data_list),
					"failed_count": failed_count,
					"saved_to": str(saved_path),
				},
				"message": "ingestion completed",
			}
		except Exception as exc:  # noqa: BLE001
			error = handle_exception(exc, logger=self.logger, context="ingestion_failed")
			return {
				"status": "error",
				"data": {"error": error},
				"message": "ingestion failed",
			}

	def _process_single_item(
		self,
		raw_item: dict[str, Any],
		enable_enhance: bool,
		chunk_size: int,
		chunk_overlap: int,
	) -> list[dict[str, Any]]:
		"""Process one raw record into multiple chunk documents."""
		source = str(raw_item.get("platform") or raw_item.get("source") or "unknown")
		item_type = str(raw_item.get("type") or "unknown")
		title = str(raw_item.get("title") or "")
		raw_text = clean_text(str(raw_item.get("content") or ""))

		if not raw_text:
			return []

		chunks = split_text_chunks(raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
		results: list[dict[str, Any]] = []

		for index, chunk in enumerate(chunks):
			final_chunk = self._enhance_content(chunk) if enable_enhance else chunk
			doc_id = generate_doc_id(
				source=source,
				content=final_chunk,
				extra=f"{item_type}:{index}:{title}",
			)

			# Metadata is prepared for downstream vector indexing and filtering.
			metadata = {
				"doc_id": doc_id,
				"source": source,
				"type": item_type,
				"title": title,
				"chunk_index": index,
				"created_at": datetime.utcnow().isoformat() + "Z",
			}

			results.append(
				{
					"doc_id": doc_id,
					"text": final_chunk,
					"metadata": metadata,
				}
			)
		return results

	def _get_qwen_client(self) -> QwenClient | None:
		if self._qwen_client is not None:
			return self._qwen_client

		try:
			self._qwen_client = QwenClient()
			return self._qwen_client
		except Exception as exc:  # noqa: BLE001
			# Enhancement is optional; missing key should not break ingestion pipeline.
			handle_exception(exc, logger=self.logger, context="init_qwen_client")
			return None

	def _enhance_content(self, text: str) -> str:
		"""Enhance chunk text with Qwen API while keeping safe fallback.

		This method intentionally keeps a lightweight implementation.
		More sophisticated prompt templates can be added later.
		"""
		client = self._get_qwen_client()
		if client is None:
			return text

		messages = [
			{
				"role": "system",
				"content": (
					"You are a data processing assistant. "
					"Improve readability while preserving factual correctness."
				),
			},
			{"role": "user", "content": text},
		]

		try:
			response = client.chat(messages=messages, temperature=0.1)
			enhanced = str(response.get("text") or "").strip()
			return enhanced or text
		except Exception as exc:  # noqa: BLE001
			handle_exception(exc, logger=self.logger, context="enhance_content")
			return text

	def _save_processed_data(self, processed_data_list: list[dict[str, Any]]) -> Path:
		target_dir = ensure_dir(self.processed_dir)
		filename = f"processed_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
		path = target_dir / filename

		payload = {
			"saved_at": datetime.utcnow().isoformat() + "Z",
			"count": len(processed_data_list),
			"items": processed_data_list,
		}
		path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
		return path
