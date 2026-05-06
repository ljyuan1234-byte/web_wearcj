from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

from core import BaseSkill, QwenClient, clean_text, handle_exception


class RagSearchSkill(BaseSkill):
	"""Hybrid retrieval skill with optional Qwen rerank."""

	name = "rag_search_skill"
	desc = "Hybrid search (dense+sparse) and rerank for precise results"

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
		query = clean_text(str(input_data.get("query") or ""))
		if not query:
			return {
				"status": "error",
				"data": {},
				"message": "query is required",
			}

		top_k = int(input_data.get("top_k", 5))
		collection_name = str(input_data.get("vector_db") or self.collection_name)

		try:
			collection = self._init_collection(collection_name)
			qwen = self._get_qwen_client()
			if qwen is None:
				return {
					"status": "error",
					"data": {},
					"message": "qwen client initialization failed",
				}

			dense_results = self._dense_retrieve(
				collection=collection,
				qwen_client=qwen,
				query=query,
				top_k=max(top_k * 2, 10),
			)
			sparse_results = self._sparse_retrieve(
				query=query,
				candidates=dense_results,
				top_k=max(top_k * 2, 10),
			)
			hybrid_results = self._merge_hybrid_results(
				dense_results=dense_results,
				sparse_results=sparse_results,
				top_k=max(top_k * 2, 10),
			)

			# Rerank is delegated to QwenClient to keep all LLM calls centralized.
			try:
				reranked = qwen.rerank(query=query, documents=hybrid_results, top_k=top_k)
			except Exception as exc:  # noqa: BLE001
				handle_exception(exc, logger=self.logger, context="rerank_failed")
				reranked = hybrid_results[:top_k]

			return {
				"status": "success",
				"data": {"query": query, "results": self._format_results(reranked)},
				"message": "search completed",
			}
		except Exception as exc:  # noqa: BLE001
			error = handle_exception(exc, logger=self.logger, context="rag_search_failed")
			return {
				"status": "error",
				"data": {"error": error},
				"message": "search failed",
			}

	def _init_collection(self, collection_name: str):
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

	def _dense_retrieve(
		self,
		collection,
		qwen_client: QwenClient,
		query: str,
		top_k: int,
	) -> list[dict[str, Any]]:
		"""Run dense retrieval with Qwen embedding vectors."""
		query_vector = qwen_client.embed_texts([query])[0]
		output = collection.query(
			query_embeddings=[query_vector],
			n_results=top_k,
			include=["documents", "metadatas", "distances"],
		)

		docs = (output.get("documents") or [[]])[0]
		metadatas = (output.get("metadatas") or [[]])[0]
		distances = (output.get("distances") or [[]])[0]
		ids = (output.get("ids") or [[]])[0]

		results: list[dict[str, Any]] = []
		for idx, doc_text in enumerate(docs):
			distance = float(distances[idx]) if idx < len(distances) else 1.0
			dense_score = 1.0 / (1.0 + distance)
			metadata = metadatas[idx] if idx < len(metadatas) else {}
			doc_id = ids[idx] if idx < len(ids) else str(metadata.get("doc_id") or f"dense_{idx}")

			results.append(
				{
					"doc_id": str(doc_id),
					"text": str(doc_text or ""),
					"metadata": metadata or {},
					"dense_score": dense_score,
				}
			)
		return results

	def _sparse_retrieve(
		self,
		query: str,
		candidates: list[dict[str, Any]],
		top_k: int,
	) -> list[dict[str, Any]]:
		"""Simple sparse scoring scaffold based on token overlap.

		This is a lightweight placeholder that can be replaced by BM25 later.
		"""
		query_tokens = set(clean_text(query).lower().split())
		scored: list[dict[str, Any]] = []

		for item in candidates:
			text_tokens = set(clean_text(str(item.get("text") or "")).lower().split())
			overlap = len(query_tokens.intersection(text_tokens))
			sparse_score = overlap / max(len(query_tokens), 1)

			merged = dict(item)
			merged["sparse_score"] = sparse_score
			scored.append(merged)

		scored.sort(key=lambda row: row.get("sparse_score", 0.0), reverse=True)
		return scored[:top_k]

	def _merge_hybrid_results(
		self,
		dense_results: list[dict[str, Any]],
		sparse_results: list[dict[str, Any]],
		top_k: int,
	) -> list[dict[str, Any]]:
		"""Merge dense and sparse scores into hybrid ranking."""
		merged_map: dict[str, dict[str, Any]] = {}

		for row in dense_results:
			doc_id = str(row.get("doc_id"))
			merged_map[doc_id] = dict(row)

		for row in sparse_results:
			doc_id = str(row.get("doc_id"))
			if doc_id not in merged_map:
				merged_map[doc_id] = dict(row)
			merged_map[doc_id]["sparse_score"] = row.get("sparse_score", 0.0)

		merged: list[dict[str, Any]] = []
		for row in merged_map.values():
			dense_score = float(row.get("dense_score", 0.0) or 0.0)
			sparse_score = float(row.get("sparse_score", 0.0) or 0.0)
			row["hybrid_score"] = (0.7 * dense_score) + (0.3 * sparse_score)
			merged.append(row)

		merged.sort(key=lambda item: item.get("hybrid_score", 0.0), reverse=True)
		return merged[:top_k]

	def _format_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
		formatted: list[dict[str, Any]] = []
		for rank, item in enumerate(results, start=1):
			formatted.append(
				{
					"rank": rank,
					"doc_id": item.get("doc_id"),
					"text": item.get("text"),
					"metadata": item.get("metadata", {}),
					"dense_score": item.get("dense_score", 0.0),
					"sparse_score": item.get("sparse_score", 0.0),
					"hybrid_score": item.get("hybrid_score", 0.0),
					"rerank_score": item.get("rerank_score", 0.0),
				}
			)
		return formatted
