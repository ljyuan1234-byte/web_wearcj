from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from core import BaseSkill, ensure_dir, generate_doc_id, handle_exception

from .helpers import crawl_comments, extract_table, safe_click, scroll_and_collect


class WebCrawlSkill(BaseSkill):
	"""Crawler skill for multi-type automotive content extraction.

	Note:
		Selectors are intentionally placeholders and should be filled later
		according to real web pages.
	"""

	name = "web_crawl_skill"
	desc = "Crawl news/specs/comments from automotive platforms with Playwright"

	def __init__(self, raw_root: str | Path = "storage/raw_data") -> None:
		super().__init__()
		self.raw_root = Path(raw_root)
		self.supported_types = {"news", "specs", "comments"}

	def version(self) -> str:
		return "1.0.0"

	def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
		"""Execute crawl flow and persist raw records.

		Input/Output follow the unified format:
		- input: dict
		- output: {"status": ..., "data": ..., "message": ...}
		"""
		platform = str(input_data.get("platform") or "").strip().lower()
		if not platform:
			return {
				"status": "error",
				"data": {},
				"message": "platform is required",
			}

		content_types = self._parse_content_types(input_data.get("content_types"))
		query = str(input_data.get("query") or "").strip()
		max_scroll = int(input_data.get("max_scroll", 3))
		max_pages = int(input_data.get("max_pages", 3))

		try:
			crawled = self._run_crawl(
				platform=platform,
				content_types=content_types,
				query=query,
				max_scroll=max_scroll,
				max_pages=max_pages,
			)
			deduped = self._deduplicate_records(crawled)
			saved_path = self._save_raw_data(platform, query, deduped)

			return {
				"status": "success",
				"data": {
					"items": deduped,
					"count": len(deduped),
					"saved_to": str(saved_path),
				},
				"message": "crawl completed",
			}
		except PlaywrightTimeoutError as exc:
			error = handle_exception(exc, logger=self.logger, context="crawl_timeout")
			return {
				"status": "error",
				"data": {"error": error},
				"message": "playwright timeout during crawling",
			}
		except Exception as exc:  # noqa: BLE001
			error = handle_exception(exc, logger=self.logger, context="crawl_failed")
			return {
				"status": "error",
				"data": {"error": error},
				"message": "unexpected crawl error",
			}

	def _parse_content_types(self, content_types: Any) -> list[str]:
		if not content_types:
			return ["news", "specs", "comments"]
		if not isinstance(content_types, list):
			raise ValueError("content_types must be a list")

		normalized = [str(item).strip().lower() for item in content_types]
		selected = [item for item in normalized if item in self.supported_types]
		if not selected:
			return ["news", "specs", "comments"]
		return list(dict.fromkeys(selected))

	def _run_crawl(
		self,
		platform: str,
		content_types: list[str],
		query: str,
		max_scroll: int,
		max_pages: int,
	) -> list[dict[str, Any]]:
		coro = self._run_crawl_async(platform, content_types, query, max_scroll, max_pages)
		try:
			return asyncio.run(coro)
		except RuntimeError as exc:
			# Fallback for environments with an active event loop.
			if "asyncio.run() cannot be called" not in str(exc):
				raise
			loop = asyncio.new_event_loop()
			try:
				return loop.run_until_complete(coro)
			finally:
				loop.close()

	async def _run_crawl_async(
		self,
		platform: str,
		content_types: list[str],
		query: str,
		max_scroll: int,
		max_pages: int,
	) -> list[dict[str, Any]]:
		results: list[dict[str, Any]] = []
		target_url = self._build_target_url(platform, query)

		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch(headless=True)
			context = await browser.new_context(
				user_agent=(
					"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
					"AppleWebKit/537.36 (KHTML, like Gecko) "
					"Chrome/124.0.0.0 Safari/537.36"
				)
			)
			page = await context.new_page()

			try:
				await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
				await page.wait_for_timeout(1200)

				if "news" in content_types:
					# Placeholder selector: fill this after real page analysis.
					await safe_click(page, None)
					news_items = await scroll_and_collect(page, None, max_scroll)
					results.extend(self._normalize_list_records(news_items, "news", platform, query))

				if "specs" in content_types:
					# Placeholder selector: fill this after real page analysis.
					specs_markdown = await extract_table(page, None)
					results.extend(
						self._normalize_specs_record(specs_markdown, platform, query)
					)

				if "comments" in content_types:
					# Placeholder selector: fill this after real page analysis.
					comment_items = await crawl_comments(page, None, max_pages)
					results.extend(
						self._normalize_list_records(comment_items, "comments", platform, query)
					)
			finally:
				await context.close()
				await browser.close()

		return results

	def _build_target_url(self, platform: str, query: str) -> str:
		base_map = {
			"autohome": "https://www.autohome.com.cn",
			"dongchedi": "https://www.dongchedi.com",
		}
		base_url = base_map.get(platform, "https://www.autohome.com.cn")
		if not query:
			return base_url
		return f"{base_url}/search?query={query}"

	def _normalize_list_records(
		self,
		records: Any,
		record_type: str,
		platform: str,
		query: str,
	) -> list[dict[str, Any]]:
		if not records:
			return []

		normalized: list[dict[str, Any]] = []
		for item in records:
			if isinstance(item, dict):
				content = str(item.get("content") or item.get("text") or "").strip()
				url = str(item.get("url") or "").strip()
				title = str(item.get("title") or "").strip()
			else:
				content = str(item).strip()
				url = ""
				title = ""

			normalized.append(
				{
					"type": record_type,
					"platform": platform,
					"query": query,
					"title": title,
					"content": content,
					"url": url,
					"crawled_at": datetime.utcnow().isoformat() + "Z",
				}
			)
		return normalized

	def _normalize_specs_record(
		self,
		markdown_text: Any,
		platform: str,
		query: str,
	) -> list[dict[str, Any]]:
		content = str(markdown_text or "").strip()
		if not content:
			return []
		return [
			{
				"type": "specs",
				"platform": platform,
				"query": query,
				"title": "vehicle_specs",
				"content": content,
				"url": "",
				"crawled_at": datetime.utcnow().isoformat() + "Z",
			}
		]

	def _deduplicate_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
		seen: set[str] = set()
		deduped: list[dict[str, Any]] = []

		for item in records:
			doc_id = generate_doc_id(
				source=f"{item.get('platform', '')}:{item.get('type', '')}",
				content=str(item.get("content") or ""),
				extra=str(item.get("url") or item.get("title") or ""),
			)
			if doc_id in seen:
				continue

			seen.add(doc_id)
			new_item = dict(item)
			new_item["doc_id"] = doc_id
			deduped.append(new_item)

		return deduped

	def _save_raw_data(self, platform: str, query: str, records: list[dict[str, Any]]) -> Path:
		target_dir = ensure_dir(self.raw_root / platform)
		filename = f"crawl_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
		path = target_dir / filename

		payload = {
			"platform": platform,
			"query": query,
			"saved_at": datetime.utcnow().isoformat() + "Z",
			"count": len(records),
			"items": records,
		}
		path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
		return path
