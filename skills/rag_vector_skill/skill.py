from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import chromadb

from core import BaseSkill, QwenClient, backup_vector_db, ensure_dir, handle_exception


class RagVectorSkill(BaseSkill):
	"""Vector indexing skill for local Chroma database."""

	name = "rag_vector_skill"
	desc = "Generate embeddings and upsert into local Chroma vector DB"

	def __init__(
		self,
		vector_db_dir: str | Path = "storage/vector_db",
		collection_name: str = "car_knowledge",
	) -> None:
		super().__init__()
		self.vector_db_dir = Path(vector_db_dir)
		self.collection_name = collection_name
		self._qwen_client: QwenClient | None = None

	def version(self) -> str:
		return "1.0.0"

	def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
		processed_data_list = input_data.get("processed_data_list")
		if not isinstance(processed_data_list, list) or not processed_data_list:
			return {
				"status": "error",
				"data": {},
				"message": "processed_data_list is required and must be a non-empty list",
			}

		collection_name = str(input_data.get("collection_name") or self.collection_name)
		batch_size = int(input_data.get("batch_size", 16))
		backup_after_insert = bool(input_data.get("backup_after_insert", True))

		try:
			collection = self._init_collection(collection_name)
			qwen = self._get_qwen_client()
			if qwen is None:
				return {
					"status": "error",
					"data": {},
					"message": "qwen client initialization failed",
				}

			inserted_count = self._upsert_in_batches(
				collection=collection,
				processed_data_list=processed_data_list,
				qwen_client=qwen,
				batch_size=batch_size,
			)

			backup_path = None
			if backup_after_insert:
				backup_path = str(
					backup_vector_db(
						vector_db_dir=self.vector_db_dir,
						backup_root="storage/backup",
					)
				)

			return {
				"status": "success",
				"data": {
					"collection_name": collection_name,
					"inserted_count": inserted_count,
					"backup_path": backup_path,
				},
				"message": "vector indexing completed",
			}
		except Exception as exc:  # noqa: BLE001
			error = handle_exception(exc, logger=self.logger, context="rag_vector_failed")
			return {
				"status": "error",
				"data": {"error": error},
				"message": "vector indexing failed",
			}

	def _init_collection(self, collection_name: str):
		"""Initialize local Chroma persistent collection."""
		ensure_dir(self.vector_db_dir)
		client = chromadb.PersistentClient(path=str(self.vector_db_dir))
		return client.get_or_create_collection(name=collection_name)

	def _get_qwen_client(self) -> QwenClient | None:
		if self._qwen_client is not None:
			return self._qwen_client

		try:
			self._qwen_client = QwenClient()
			return self._qwen_client
		except Exception as exc:  # noqa: BLE001
			handle_exception(exc, logger=self.logger, context="init_qwen_client")
			return None

	def _upsert_in_batches(
		self,
		collection,
		processed_data_list: list[dict[str, Any]],
		qwen_client: QwenClient,
		batch_size: int,
	) -> int:
		"""Batch embedding generation and Chroma upsert.

		This method keeps a clear framework and can be extended with
		advanced validation and idempotency rules later.
		"""
		inserted_count = 0
		for start in range(0, len(processed_data_list), batch_size):
			batch = processed_data_list[start : start + batch_size]
			texts = [str(item.get("text") or "") for item in batch]

			embeddings = self._embed_with_retry(
				qwen_client=qwen_client,
				texts=texts,
				max_retries=2,
			)

			ids = [str(item.get("doc_id") or f"doc_{start + idx}") for idx, item in enumerate(batch)]
			metadatas = [self._normalize_metadata(item.get("metadata", {})) for item in batch]

			collection.upsert(
				ids=ids,
				documents=texts,
				embeddings=embeddings,
				metadatas=metadatas,
			)
			inserted_count += len(batch)
		return inserted_count

	def _embed_with_retry(
		self,
		qwen_client: QwenClient,
		texts: list[str],
		max_retries: int,
	) -> list[list[float]]:
		"""Generate embeddings with retry strategy for API resilience."""
		last_exc: Exception | None = None
		for attempt in range(max_retries + 1):
			try:
				return qwen_client.embed_texts(texts)
			except Exception as exc:  # noqa: BLE001
				last_exc = exc
				if attempt >= max_retries:
					raise
				time.sleep(min(2**attempt, 4))
		raise RuntimeError(str(last_exc or "embedding failed"))

	def _normalize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
		"""Convert metadata into Chroma-safe primitive values."""
		normalized: dict[str, Any] = {}
		for key, value in metadata.items():
			if isinstance(value, (str, int, float, bool)) or value is None:
				normalized[key] = value
			else:
				normalized[key] = str(value)
		return normalized
