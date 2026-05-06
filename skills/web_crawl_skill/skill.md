# WebCrawlSkill

## Version
- 1.0.0

## Purpose
- Crawl automotive platform pages according to `content_types`.
- Support three categories: `news`, `specs`, `comments`.
- Use Playwright for dynamic rendering.
- Include duplicate filtering and anti-bot friendly behavior.

## Input
- `platform` (required, string): target source, for example `autohome` or `dongchedi`.
- `content_types` (optional, list[str]): subset of `news/specs/comments`. Default is all three.
- `query` (optional, string): keyword for platform search pages.
- `max_scroll` (optional, int): max scroll rounds for feed pages.
- `max_pages` (optional, int): max pages for comments crawling.

## Output
- Dictionary with keys `status`, `data`, `message`.
- `data.items` is a list of crawled records.
- Every record contains a `type` tag (`news/specs/comments`) and normalized metadata.

## Runtime Notes
- The current helper selectors are placeholders by design.
- Real selectors should be filled later based on real platform DOM structure.

## Error Handling
- Parameter validation errors return `status=error`.
- Browser timeout and navigation errors are captured and returned.
- Unexpected errors are normalized for upstream workflow handling.
