from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .utils import get_logger, handle_exception


class SkillError(Exception):
	"""Skill base error."""


@dataclass(frozen=True)
class SkillVersion:
	"""Callable wrapper keeps version as class attribute while supporting version()."""

	value: str

	def __call__(self) -> str:
		return self.value

	def __str__(self) -> str:
		return self.value


class BaseSkill(ABC):
	"""Base class for all skills.

	Subclasses should override class attributes and implement run().
	"""

	name = "base_skill"
	desc = "Base skill for standardized execution"
	version = SkillVersion("0.1.0")

	def __init_subclass__(cls, **kwargs: Any) -> None:
		super().__init_subclass__(**kwargs)
		declared = cls.__dict__.get("version")
		if isinstance(declared, str):
			cls.version = SkillVersion(declared)

	def __init__(self) -> None:
		self.logger = get_logger(self.__class__.__name__)

	@abstractmethod
	def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
		"""Execute skill core logic.

		All skills must return a dict payload.
		"""

	def execute(self, input_data: dict[str, Any] | None) -> dict[str, Any]:
		"""Standardized execution entry with exception handling."""
		trace_id = str(uuid4())
		normalized_input = self.normalize_input(input_data or {}, trace_id=trace_id)
		try:
			result = self.run(normalized_input)
			return self.normalize_output(result, trace_id=trace_id)
		except Exception as exc:  # noqa: BLE001
			error = handle_exception(
				exc,
				logger=self.logger,
				context=f"skill={self.name} trace_id={trace_id}",
			)
			return {
				"ok": False,
				"skill": self.name,
				"version": self.version(),
				"trace_id": trace_id,
				"result": None,
				"error": error,
				"meta": {},
			}

	def normalize_input(
		self,
		input_data: dict[str, Any],
		trace_id: str,
	) -> dict[str, Any]:
		"""Normalize input for Qwen function-calling style data exchange."""
		messages = input_data.get("messages")
		if not messages and input_data.get("query"):
			messages = [{"role": "user", "content": str(input_data["query"])}]

		function_call = input_data.get("function_call") or {}
		standardized = {
			"trace_id": trace_id,
			"query": str(input_data.get("query") or input_data.get("input") or ""),
			"messages": messages or [],
			"context": input_data.get("context") or {},
			"meta": input_data.get("meta") or {},
			"function_call": {
				"name": function_call.get("name", ""),
				"arguments": function_call.get("arguments", {})
				if isinstance(function_call.get("arguments", {}), dict)
				else {"raw": function_call.get("arguments")},
			},
		}
		return standardized

	def normalize_output(
		self,
		output_data: dict[str, Any],
		trace_id: str,
	) -> dict[str, Any]:
		"""Normalize skill output to a unified schema."""
		if not isinstance(output_data, dict):
			raise SkillError("Skill output must be a dict")

		return {
			"ok": bool(output_data.get("ok", True)),
			"skill": self.name,
			"version": self.version(),
			"trace_id": trace_id,
			"result": output_data.get("result", output_data),
			"error": output_data.get("error"),
			"meta": output_data.get("meta", {}),
		}

	def build_function_result(
		self,
		function_name: str,
		arguments: dict[str, Any],
		result: Any,
	) -> dict[str, Any]:
		"""Build normalized payload for Qwen function-calling returns."""
		return {
			"ok": True,
			"result": {
				"function_name": function_name,
				"arguments": arguments,
				"output": result,
			},
			"meta": {},
		}
