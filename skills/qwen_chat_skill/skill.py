from __future__ import annotations

import uuid
from typing import Any

from core import (
	BaseSkill,
	QwenClient,
	handle_exception,
	load_chat_history,
	save_chat_history,
)


class QwenChatSkill(BaseSkill):
	"""Chat generation skill for automotive QA and assistant responses."""

	name = "qwen_chat_skill"
	desc = "Generate chat answers from query and retrieval context"

	def __init__(self) -> None:
		super().__init__()
		self._qwen_client: QwenClient | None = None
		self.system_prompt = (
			"You are a professional automotive assistant. "
			"Provide concise, factual, and user-friendly answers."
		)

	def version(self) -> str:
		return "1.0.0"

	def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
		query = str(input_data.get("query") or "").strip()
		if not query:
			return {
				"status": "error",
				"data": {},
				"message": "query is required",
			}

		session_id = str(input_data.get("session_id") or uuid.uuid4().hex)
		retrieval_results = input_data.get("retrieval_results") or []

		try:
			history = input_data.get("history")
			if history is None:
				history = load_chat_history(session_id)

			qwen = self._get_qwen_client()
			if qwen is None:
				return {
					"status": "error",
					"data": {},
					"message": "qwen client initialization failed",
				}

			messages = self._build_messages(
				query=query,
				retrieval_results=retrieval_results,
				history=history,
			)

			enable_fc = bool(input_data.get("enable_function_calling", False))
			functions = input_data.get("functions") or []

			if enable_fc and functions:
				# Function-calling decision is delegated to QwenClient.
				response = qwen.decide_function_call(
					user_query=query,
					functions=functions,
					history_messages=messages[:-1],
				)
			else:
				response = qwen.chat(
					messages=messages,
					temperature=float(input_data.get("temperature", 0.3)),
				)

			answer = self._format_answer(response)
			new_history = history + [
				{"role": "user", "content": query},
				{"role": "assistant", "content": answer},
			]
			save_chat_history(session_id=session_id, messages=new_history)

			return {
				"status": "success",
				"data": {
					"answer": answer,
					"session_id": session_id,
					"tool_calls": response.get("tool_calls", []),
					"token_usage": qwen.get_token_usage(),
				},
				"message": "chat completed",
			}
		except Exception as exc:  # noqa: BLE001
			error = handle_exception(exc, logger=self.logger, context="qwen_chat_failed")
			return {
				"status": "error",
				"data": {"error": error},
				"message": "chat failed",
			}

	def _get_qwen_client(self) -> QwenClient | None:
		if self._qwen_client is not None:
			return self._qwen_client
		try:
			self._qwen_client = QwenClient()
			return self._qwen_client
		except Exception as exc:  # noqa: BLE001
			handle_exception(exc, logger=self.logger, context="init_qwen_client")
			return None

	def _build_messages(
		self,
		query: str,
		retrieval_results: list[dict[str, Any]],
		history: list[dict[str, Any]],
	) -> list[dict[str, str]]:
		"""Build model input messages with retrieval context and dialogue history."""
		context_text = self._format_retrieval_context(retrieval_results)

		messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
		if context_text:
			messages.append(
				{
					"role": "system",
					"content": f"Reference context:\n{context_text}",
				}
			)

		# History should be role/content dictionaries compatible with chat API.
		for item in history:
			role = str(item.get("role") or "").strip()
			content = str(item.get("content") or "").strip()
			if role in {"user", "assistant", "system"} and content:
				messages.append({"role": role, "content": content})

		messages.append({"role": "user", "content": query})
		return messages

	def _format_retrieval_context(self, retrieval_results: list[dict[str, Any]]) -> str:
		if not retrieval_results:
			return ""

		lines: list[str] = []
		for index, item in enumerate(retrieval_results, start=1):
			text = str(item.get("text") or "").strip()
			if not text:
				continue
			source = str(item.get("metadata", {}).get("source") or "unknown")
			lines.append(f"[{index}] source={source} text={text}")
		return "\n".join(lines)

	def _format_answer(self, response: dict[str, Any]) -> str:
		"""Format plain answer and preserve tool-call hints for future orchestration."""
		answer = str(response.get("text") or "").strip()
		tool_calls = response.get("tool_calls") or []
		if answer:
			return answer
		if tool_calls:
			return "Model suggests tool execution. Please execute tool calls in orchestration layer."
		return "No response generated."
