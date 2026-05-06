# RagSearchSkill

## Version
- 1.0.0

## Purpose
- Accept user query and execute hybrid retrieval.
- Combine dense retrieval and sparse lexical scoring.
- Use Qwen rerank for final precision ordering.

## Dependencies
- Chroma local vector database
- Qwen API wrapper in core/qwen_client.py

## Input
- `query` (required, string): user query.
- `vector_db` (optional, string): collection name override.
- `top_k` (optional, int): final result size.

## Output
- Dictionary with keys `status`, `data`, `message`.
- `data.results` is final ordered retrieval list.

## Error Handling
- Empty query returns parameter error.
- Vector DB access failures are captured.
- Rerank failures fallback to available hybrid scores.
