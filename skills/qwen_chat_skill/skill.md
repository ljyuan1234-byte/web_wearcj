# QwenChatSkill

## Version
- 1.0.0

## Purpose
- Generate automotive-domain conversational answers using Qwen API.
- Accept user query, optional retrieval context, and optional history.
- Support history load/save and optional function-calling decision.

## Dependencies
- Qwen API wrapper in core/qwen_client.py
- History and prompt helpers in core/utils.py

## Input
- `query` (required, string): user question.
- `retrieval_results` (optional, list[dict]): retrieval context records.
- `history` (optional, list[dict]): dialogue history; if absent, load by session id.
- `session_id` (optional, string): history file key.
- `functions` (optional, list[dict]): function-calling schema.
- `enable_function_calling` (optional, bool): enable tool routing decision.

## Output
- Dictionary with keys `status`, `data`, `message`.
- `data.answer` contains model response.
- `data.session_id` for history tracking.

## Error Handling
- Empty query returns parameter error.
- Qwen API failures are normalized and returned.
- History persistence failures are captured in error payload.
