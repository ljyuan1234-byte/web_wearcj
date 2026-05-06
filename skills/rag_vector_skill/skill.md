# RagVectorSkill

## Version
- 1.0.0

## Purpose
- Receive ingestion chunks and generate embeddings via Qwen API.
- Store vectors into local Chroma database.
- Support vector database backup after insertion.

## Dependencies
- Chroma local persistent client
- Qwen API wrapper in core/qwen_client.py

## Input
- `processed_data_list` (required, list[dict]): processed chunk records.
- `collection_name` (optional, string): target collection name.
- `batch_size` (optional, int): embedding batch size.
- `backup_after_insert` (optional, bool): whether to trigger vector DB backup.

## Output
- Dictionary with keys `status`, `data`, `message`.
- `data.inserted_count` indicates successful insertion count.

## Error Handling
- Invalid input returns parameter error.
- Embedding generation supports retries.
- Chroma write failures are captured and normalized.
