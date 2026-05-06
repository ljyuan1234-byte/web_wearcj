# IngestionSkill

## Version
- 1.0.0

## Purpose
- Process crawler raw records into retrieval-ready chunks.
- Complete text cleaning, chunk split, content enhancement, and metadata enrichment.

## Dependencies
- Qwen API via core/qwen_client.py
- Common utilities in core/utils.py

## Input
- `raw_data_list` (required, list[dict]): raw records from crawler.
- `enable_enhance` (optional, bool): whether to call Qwen for content enhancement.
- `chunk_size` (optional, int): split size.
- `chunk_overlap` (optional, int): overlap size.

## Output
- Dictionary with keys `status`, `data`, `message`.
- `data.processed_data_list` includes normalized chunk records.

## Error Handling
- Missing/invalid `raw_data_list` returns parameter error.
- Single-record processing failures are isolated and do not break whole batch.
- Qwen call failures fallback to original text and log warning.
