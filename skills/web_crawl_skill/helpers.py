async def scroll_and_collect(page, container_selector, max_scroll):
	"""Scroll feed pages and collect card-level records.

	Args:
		page: Playwright page instance.
		container_selector: CSS selector for feed container.
		max_scroll: Maximum number of scroll rounds.

	Returns:
		A list of collected records.
	"""
	pass


async def extract_table(page, table_selector):
	"""Extract an HTML table from page and convert it to Markdown text.

	Args:
		page: Playwright page instance.
		table_selector: CSS selector for target table.

	Returns:
		Markdown representation of table content.
	"""
	pass


async def crawl_comments(page, section_selector, max_pages):
	"""Crawl user comments from paginated sections.

	Args:
		page: Playwright page instance.
		section_selector: CSS selector for comment section.
		max_pages: Maximum number of pages to iterate.

	Returns:
		A list of comment records.
	"""
	pass


async def safe_click(page, selector):
	"""Safely wait and click target node when selector is available.

	Args:
		page: Playwright page instance.
		selector: CSS selector for click target.
	"""
	pass
