from __future__ import annotations

import time
from typing import Any

import chromadb
import streamlit as st
from celery.result import AsyncResult

import config
from core import QwenClient
from tasks.crawl_tasks import crawl_and_process
from tasks.celery_app import celery_app


def _password_guard() -> None:
	"""When UI_PASSWORD exists, require password before entering the app."""
	expected_password = str(config.UI_PASSWORD or "").strip()
	if not expected_password:
		return

	if "auth_passed" not in st.session_state:
		st.session_state.auth_passed = False

	if st.session_state.auth_passed:
		return

	st.title("Car RAG Agent")
	st.subheader("访问保护")
	st.info("请输入访问密码后继续。")

	password = st.text_input("UI Password", type="password")
	if st.button("验证密码"):
		if password == expected_password:
			st.session_state.auth_passed = True
			st.success("验证通过，正在进入主界面。")
			st.rerun()
		else:
			st.error("密码错误，请重试。")

	st.stop()


def _get_qwen_client() -> QwenClient | None:
	if "qwen_client" in st.session_state:
		return st.session_state.qwen_client

	try:
		st.session_state.qwen_client = QwenClient()
		return st.session_state.qwen_client
	except Exception as exc:  # noqa: BLE001
		st.sidebar.error(f"QwenClient 初始化失败: {exc}")
		st.session_state.qwen_client = None
		return None


def _check_api_connectivity() -> tuple[bool, str]:
	client = _get_qwen_client()
	if client is None:
		return False, "QwenClient 不可用，请检查 QWEN_API_KEY 配置。"

	try:
		response = client.chat(
			messages=[
				{"role": "system", "content": "You are a helpful assistant."},
				{"role": "user", "content": "ping"},
			],
			temperature=0.0,
		)
		if response.get("ok"):
			return True, "API 连通正常"
		return False, "API 返回异常"
	except Exception as exc:  # noqa: BLE001
		return False, f"API 连通失败: {exc}"


def _check_chroma_status() -> tuple[bool, str]:
	try:
		client = chromadb.PersistentClient(path=str(config.VECTOR_DB_DIR))
		collections = client.list_collections()
		names = [item.name for item in collections]
		return True, f"Chroma 正常，集合数: {len(names)}"
	except Exception as exc:  # noqa: BLE001
		return False, f"Chroma 异常: {exc}"


def _render_sidebar() -> None:
	st.sidebar.header("系统状态")

	if st.sidebar.button("检测 API 连通性"):
		ok, message = _check_api_connectivity()
		st.session_state.api_status = {"ok": ok, "message": message}

	if st.sidebar.button("检测 Chroma 状态"):
		ok, message = _check_chroma_status()
		st.session_state.chroma_status = {"ok": ok, "message": message}

	api_status = st.session_state.get("api_status")
	chroma_status = st.session_state.get("chroma_status")

	if api_status:
		if api_status["ok"]:
			st.sidebar.success(api_status["message"])
		else:
			st.sidebar.error(api_status["message"])

	if chroma_status:
		if chroma_status["ok"]:
			st.sidebar.success(chroma_status["message"])
		else:
			st.sidebar.error(chroma_status["message"])

	st.sidebar.subheader("当前会话 Token 用量")
	qwen_client = _get_qwen_client()
	usage = (
		qwen_client.get_token_usage()
		if qwen_client is not None
		else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
	)

	total_tokens = int(usage.get("total_tokens", 0))
	token_limit = max(int(config.MAX_CHAT_TOKENS), 1)
	ratio = min(total_tokens / token_limit, 1.0)

	st.sidebar.write(
		f"Prompt: {usage.get('prompt_tokens', 0)} | "
		f"Completion: {usage.get('completion_tokens', 0)}"
	)
	st.sidebar.write(f"Total: {total_tokens} / {token_limit}")
	st.sidebar.progress(ratio)


def _submit_crawl_tasks(
	platforms: list[str],
	content_types: list[str],
	query: str,
) -> None:
	"""Submit one Celery task per platform and cache task ids in session state."""
	submitted: list[str] = []
	for platform in platforms:
		async_result = crawl_and_process.delay(
			platform=platform,
			content_types=content_types,
			query=query,
			options={
				"chunk_size": config.INGESTION_CHUNK_SIZE,
				"chunk_overlap": config.INGESTION_CHUNK_OVERLAP,
				"batch_size": config.VECTOR_EMBED_BATCH_SIZE,
			},
		)
		submitted.append(async_result.id)

	st.session_state.crawl_task_ids = submitted
	st.session_state.last_submitted_at = time.time()


def _read_task_result(task_id: str) -> dict[str, Any]:
	result = AsyncResult(task_id, app=celery_app)
	state = result.state
	payload: dict[str, Any] = {
		"task_id": task_id,
		"state": state,
		"meta": result.info if isinstance(result.info, dict) else {},
		"result": None,
	}

	if state == "SUCCESS":
		payload["result"] = result.result
	elif state == "FAILURE":
		payload["result"] = str(result.info)

	return payload


def _render_crawl_tab() -> None:
	st.subheader("爬取与处理（Celery 异步）")

	platforms = st.multiselect(
		"选择平台（可多选）",
		options=["autohome", "dongchedi"],
		default=config.CRAWL_DEFAULT_PLATFORMS,
	)
	content_types = st.multiselect(
		"选择内容类型（可多选）",
		options=["news", "specs", "comments"],
		default=config.CRAWL_DEFAULT_CONTENT_TYPES,
	)
	query = st.text_input("关键词（可选）", value="")

	if st.button("开始爬取"):
		if not platforms:
			st.error("请至少选择一个平台。")
		elif not content_types:
			st.error("请至少选择一个内容类型。")
		else:
			_submit_crawl_tasks(platforms, content_types, query)
			st.success("任务已提交，正在异步执行爬取 -> 处理 -> 入库链路。")

	task_ids = st.session_state.get("crawl_task_ids", [])
	if not task_ids:
		st.info("尚未提交任务。")
		return

	st.markdown("### 任务状态")
	rows: list[dict[str, Any]] = []
	unfinished = 0
	for task_id in task_ids:
		item = _read_task_result(task_id)
		state = item["state"]
		meta = item.get("meta", {})
		result = item.get("result")

		if state not in {"SUCCESS", "FAILURE", "REVOKED"}:
			unfinished += 1

		rows.append(
			{
				"task_id": task_id,
				"state": state,
				"step": meta.get("step", ""),
				"message": meta.get("message", ""),
				"result_preview": str(result)[:120] if result is not None else "",
			}
		)

	st.dataframe(rows, use_container_width=True)

	auto_poll = st.checkbox("自动轮询任务状态", value=True)
	if auto_poll and unfinished > 0:
		st.caption(
			f"仍有 {unfinished} 个任务运行中，将在 "
			f"{config.UI_TASK_POLL_INTERVAL_SECONDS} 秒后刷新。"
		)
		time.sleep(config.UI_TASK_POLL_INTERVAL_SECONDS)
		st.rerun()


def _render_search_tab() -> None:
	# 该标签页保留原有能力入口；当前仅展示占位。
	st.subheader("检索")
	st.info("检索标签页逻辑保持不变，可接入现有 RagSearchSkill 调度流程。")


def _render_chat_tab() -> None:
	# 该标签页保留原有能力入口；当前仅展示占位。
	st.subheader("对话")
	st.info("对话标签页逻辑保持不变，可接入现有 QwenChatSkill 调度流程。")


def main() -> None:
	st.set_page_config(page_title="Car RAG Agent", page_icon="CAR", layout="wide")

	_password_guard()
	st.title("Car RAG Agent 控制台")
	_render_sidebar()

	tab_crawl, tab_search, tab_chat = st.tabs(["爬取", "检索", "对话"])
	with tab_crawl:
		_render_crawl_tab()
	with tab_search:
		_render_search_tab()
	with tab_chat:
		_render_chat_tab()


if __name__ == "__main__":
	main()
