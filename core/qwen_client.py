from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha1
from math import sqrt
from typing import Any

import requests

from .utils import clean_text, get_logger, handle_exception, split_text_chunks


class QwenClientError(Exception):
	"""Base qwen client error."""


class QwenConfigError(QwenClientError):
	"""Configuration related qwen client error."""


class QwenAuthenticationError(QwenClientError):
	"""Authentication related qwen client error."""


class QwenRateLimitError(QwenClientError):
	"""Rate limit related qwen client error."""


class QwenAPIError(QwenClientError):
	"""Remote API related qwen client error."""


@dataclass
class RequestMetric:
	endpoint: str
	latency_ms: float
	success: bool


class QwenClient:
	"""Qwen API wrapper for chat, function-calling, embedding, retrieve and rerank."""

	def __init__(
		self,
		api_key: str | None = None,
		base_url: str | None = None,
		chat_model: str | None = None,
		embedding_model: str | None = None,
		rerank_model: str | None = None,
		timeout: int | None = None,
		max_chat_tokens: int | None = None,
		max_retries: int = 2,
		enable_cache: bool = True,
	) -> None:
		self.logger = get_logger("qwen_client")

		self.api_key = api_key or self._read_config("QWEN_API_KEY")
		if not self.api_key:
			raise QwenConfigError(
				"Qwen API Key 未配置。请在 config.py 中设置 QWEN_API_KEY，或在 .env/环境变量中提供 QWEN_API_KEY。"
			)

		self.base_url = (
			base_url
			or self._read_config("QWEN_API_BASE_URL")
			or "https://dashscope.aliyuncs.com/compatible-mode/v1"
		).rstrip("/")
		self.chat_model = chat_model or self._read_config("QWEN_CHAT_MODEL") or "qwen-plus"
		self.embedding_model = (
			embedding_model
			or self._read_config("QWEN_EMBEDDING_MODEL")
			or "text-embedding-v2"
		)
		self.rerank_model = rerank_model or self._read_config("QWEN_RERANK_MODEL") or "gte-rerank"
		self.timeout = int(timeout or self._read_config("QWEN_TIMEOUT") or 60)
		self.max_chat_tokens = int(
			max_chat_tokens or self._read_config("MAX_CHAT_TOKENS") or 200_000
		)
		self.max_retries = max_retries
		self.enable_cache = enable_cache

		self._cache: dict[str, Any] = {}
		self._metrics: list[RequestMetric] = []
		self._prompt_tokens = 0
		self._completion_tokens = 0
		self._total_tokens = 0

	@staticmethod
	def _read_config(key: str) -> Any:
		"""Read config value from config.py first, then environment variables."""
		config_value: Any = None
		try:
			import config  # type: ignore

			if hasattr(config, key):
				config_value = getattr(config, key)
			elif hasattr(config, key.lower()):
				config_value = getattr(config, key.lower())
		except Exception:  # noqa: BLE001
			config_value = None

		if config_value in (None, ""):
			return os.getenv(key)
		return config_value

	@staticmethod
	def _cache_key(namespace: str, payload: dict[str, Any]) -> str:
		normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
		return f"{namespace}:{sha1(normalized.encode('utf-8')).hexdigest()}"

	def _headers(self) -> dict[str, str]:
		return {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json",
		}

	def _record_metric(self, endpoint: str, start_time: float, success: bool) -> None:
		latency_ms = (time.perf_counter() - start_time) * 1000
		self._metrics.append(RequestMetric(endpoint=endpoint, latency_ms=latency_ms, success=success))

	def _request(
		self,
		endpoint: str,
		payload: dict[str, Any],
		use_cache: bool = False,
		cache_namespace: str = "default",
	) -> dict[str, Any]:
		cache_key = self._cache_key(cache_namespace, payload)
		if use_cache and self.enable_cache and cache_key in self._cache:
			return self._cache[cache_key]

		url = f"{self.base_url}/{endpoint.lstrip('/')}"
		last_exc: Exception | None = None

		for attempt in range(self.max_retries + 1):
			started = time.perf_counter()
			try:
				response = requests.post(
					url,
					headers=self._headers(),
					json=payload,
					timeout=self.timeout,
				)
				if response.status_code == 401:
					raise QwenAuthenticationError("Qwen API 鉴权失败，请检查 QWEN_API_KEY。")
				if response.status_code == 429:
					raise QwenRateLimitError("Qwen API 触发限流，请稍后重试。")
				if response.status_code >= 400:
					raise QwenAPIError(
						f"Qwen API 请求失败，status={response.status_code} body={response.text}"
					)

				data: dict[str, Any] = response.json()
				self._update_token_usage(data)
				self._record_metric(endpoint, started, success=True)

				if use_cache and self.enable_cache:
					self._cache[cache_key] = data
				return data
			except (QwenAuthenticationError, QwenRateLimitError, QwenAPIError) as exc:
				last_exc = exc
				self._record_metric(endpoint, started, success=False)
				if attempt >= self.max_retries:
					raise
				time.sleep(min(2**attempt, 4))
			except requests.RequestException as exc:
				last_exc = QwenAPIError(f"网络请求失败: {exc}")
				self._record_metric(endpoint, started, success=False)
				if attempt >= self.max_retries:
					raise last_exc
				time.sleep(min(2**attempt, 4))

		raise QwenAPIError(str(last_exc or "Unknown API error"))

	def _update_token_usage(self, data: dict[str, Any]) -> None:
		usage = data.get("usage") or {}
		prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
		completion_tokens = int(usage.get("completion_tokens", 0) or 0)
		total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)

		self._prompt_tokens += prompt_tokens
		self._completion_tokens += completion_tokens
		self._total_tokens += total_tokens

	def get_token_usage(self) -> dict[str, int]:
		"""Return accumulated token usage for current client session."""
		return {
			"prompt_tokens": self._prompt_tokens,
			"completion_tokens": self._completion_tokens,
			"total_tokens": self._total_tokens,
		}

	def check_cost_limit(self, max_chat_tokens: int | None = None) -> bool:
		"""Check token budget and log warning at 80% threshold."""
		limit = int(max_chat_tokens or self.max_chat_tokens)
		usage = self._total_tokens
		if usage >= int(limit * 0.8):
			self.logger.warning(
				"Token usage is high: %s/%s (%.2f%%)",
				usage,
				limit,
				(usage / limit) * 100 if limit else 0,
			)
		if usage > limit:
			self.logger.error("Token usage exceeded limit: %s/%s", usage, limit)
			return False
		return True

	def chat(
		self,
		messages: list[dict[str, Any]],
		model: str | None = None,
		temperature: float = 0.2,
		tools: list[dict[str, Any]] | None = None,
		tool_choice: str | dict[str, Any] | None = None,
	) -> dict[str, Any]:
		"""Call Qwen chat completion endpoint."""
		payload: dict[str, Any] = {
			"model": model or self.chat_model,
			"messages": messages,
			"temperature": temperature,
		}
		if tools:
			payload["tools"] = tools
		if tool_choice:
			payload["tool_choice"] = tool_choice

		data = self._request(
			endpoint="chat/completions",
			payload=payload,
			use_cache=True,
			cache_namespace="chat",
		)

		choice = ((data.get("choices") or [{}])[0])
		message = choice.get("message") or {}
		content = message.get("content", "")
		tool_calls = message.get("tool_calls", [])

		return {
			"ok": True,
			"text": content,
			"tool_calls": tool_calls,
			"usage": data.get("usage", {}),
			"raw": data,
		}

	def batch_chat(
		self,
		messages_batch: list[list[dict[str, Any]]],
		model: str | None = None,
		temperature: float = 0.2,
	) -> list[dict[str, Any]]:
		"""Batch process chat requests sequentially for observability and retry safety."""
		results: list[dict[str, Any]] = []
		for messages in messages_batch:
			try:
				results.append(self.chat(messages=messages, model=model, temperature=temperature))
			except Exception as exc:  # noqa: BLE001
				results.append(handle_exception(exc, logger=self.logger, context="batch_chat"))
		return results

	def decide_function_call(
		self,
		user_query: str,
		functions: list[dict[str, Any]],
		history_messages: list[dict[str, Any]] | None = None,
	) -> dict[str, Any]:
		"""Use function-calling to decide which tool/skill should run."""
		tools = [{"type": "function", "function": item} for item in functions]
		messages = (history_messages or []) + [{"role": "user", "content": user_query}]
		return self.chat(messages=messages, tools=tools, tool_choice="auto")

	def split_text(
		self,
		text: str,
		chunk_size: int = 800,
		chunk_overlap: int = 100,
	) -> list[str]:
		"""Text splitting helper for ingestion pipeline."""
		return split_text_chunks(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

	def _iter_batches(self, data: list[Any], batch_size: int) -> list[list[Any]]:
		if batch_size <= 0:
			raise ValueError("batch_size must be greater than 0")
		return [data[index : index + batch_size] for index in range(0, len(data), batch_size)]

	def embed_texts(
		self,
		texts: list[str],
		model: str | None = None,
		batch_size: int = 16,
	) -> list[list[float]]:
		"""Create embeddings in batches."""
		if not texts:
			return []

		vectors: list[list[float]] = []
		for batch in self._iter_batches(texts, batch_size=batch_size):
			payload = {
				"model": model or self.embedding_model,
				"input": [clean_text(text) for text in batch],
			}
			data = self._request(
				endpoint="embeddings",
				payload=payload,
				use_cache=True,
				cache_namespace="embedding",
			)
			items = data.get("data", [])
			vectors.extend([item.get("embedding", []) for item in items])
		return vectors

	@staticmethod
	def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
		if not vec_a or not vec_b or len(vec_a) != len(vec_b):
			return 0.0
		dot = sum(a * b for a, b in zip(vec_a, vec_b))
		norm_a = sqrt(sum(a * a for a in vec_a))
		norm_b = sqrt(sum(b * b for b in vec_b))
		if norm_a == 0 or norm_b == 0:
			return 0.0
		return dot / (norm_a * norm_b)

	def retrieve(
		self,
		query_vector: list[float],
		candidates: list[dict[str, Any]],
		top_k: int = 5,
	) -> list[dict[str, Any]]:
		"""Retrieve top-k candidate documents by cosine similarity."""
		scored: list[dict[str, Any]] = []
		for doc in candidates:
			score = self._cosine_similarity(query_vector, doc.get("embedding", []))
			new_doc = dict(doc)
			new_doc["score"] = score
			scored.append(new_doc)

		scored.sort(key=lambda item: item.get("score", 0), reverse=True)
		return scored[:top_k]

	def rerank(
		self,
		query: str,
		documents: list[dict[str, Any]],
		top_k: int = 5,
		model: str | None = None,
	) -> list[dict[str, Any]]:
		"""Rerank candidates by remote API, fallback to local lexical scoring."""
		if not documents:
			return []

		payload = {
			"model": model or self.rerank_model,
			"query": query,
			"documents": [item.get("text", "") for item in documents],
		}
		try:
			data = self._request(
				endpoint="rerank",
				payload=payload,
				use_cache=True,
				cache_namespace="rerank",
			)
			ranks = data.get("results", [])
			score_map = {item.get("index"): item.get("relevance_score", 0) for item in ranks}
			merged: list[dict[str, Any]] = []
			for index, doc in enumerate(documents):
				new_doc = dict(doc)
				new_doc["rerank_score"] = score_map.get(index, 0)
				merged.append(new_doc)
			merged.sort(key=lambda item: item.get("rerank_score", 0), reverse=True)
			return merged[:top_k]
		except Exception as exc:  # noqa: BLE001
			self.logger.warning("Remote rerank failed, fallback to lexical ranking: %s", exc)

		query_tokens = set(clean_text(query).lower().split())
		fallback = []
		for doc in documents:
			text_tokens = set(clean_text(str(doc.get("text", ""))).lower().split())
			overlap = len(query_tokens.intersection(text_tokens))
			item = dict(doc)
			item["rerank_score"] = overlap
			fallback.append(item)

		fallback.sort(key=lambda item: item.get("rerank_score", 0), reverse=True)
		return fallback[:top_k]

	def get_monitoring_stats(self) -> dict[str, Any]:
		"""Expose API call monitoring stats for observability."""
		total = len(self._metrics)
		success = len([metric for metric in self._metrics if metric.success])
		avg_latency = (
			sum(metric.latency_ms for metric in self._metrics) / total if total else 0
		)
		return {
			"total_requests": total,
			"success_requests": success,
			"failed_requests": total - success,
			"avg_latency_ms": round(avg_latency, 2),
		}
