from __future__ import annotations

import os
from secrets import compare_digest
from typing import Any

import requests
import streamlit as st

API_URL = os.getenv("DOCOPS_API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("DOCOPS_API_KEY", "").strip()
UI_PASSWORD = os.getenv("DOCOPS_UI_PASSWORD", "")
JsonPayload = dict[str, Any] | list[dict[str, Any]]


def _request_json(method: str, path: str, **kwargs: Any) -> JsonPayload | None:
    headers = dict(kwargs.pop("headers", {}))
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    try:
        response = requests.request(
            method,
            f"{API_URL}{path}",
            headers=headers,
            timeout=60,
            **kwargs,
        )
    except requests.RequestException as exc:
        st.error(f"无法连接 DocOps API：{exc}")
        return None

    try:
        payload = response.json()
    except requests.JSONDecodeError:
        payload = None
    if not response.ok:
        detail = payload.get("detail") if isinstance(payload, dict) else response.text
        st.error(f"请求失败（{response.status_code}）：{detail or '未知错误'}")
        return None
    if not isinstance(payload, (dict, list)):
        st.error("DocOps API 返回了无法识别的响应。")
        return None
    return payload


def _post_json(path: str, **kwargs: Any) -> dict[str, Any] | None:
    payload = _request_json("POST", path, **kwargs)
    if payload is not None and not isinstance(payload, dict):
        st.error("DocOps API 返回了类型错误的响应。")
        return None
    return payload


def _load_documents() -> None:
    payload = _request_json("GET", "/documents")
    if isinstance(payload, list):
        st.session_state["documents"] = payload


def _render_answer(answer: dict[str, Any]) -> None:
    st.caption(f"置信度：{answer['confidence']:.2f}")
    for index, citation in enumerate(answer.get("citations", []), start=1):
        page = citation.get("page") or "?"
        with st.expander(f"[{index}] {citation['title']} · 第 {page} 页"):
            st.write(citation["quote"])


def _render_result(result: dict[str, Any]) -> None:
    st.write(result["message"])
    answer = result.get("answer")
    if isinstance(answer, dict):
        _render_answer(answer)


st.set_page_config(page_title="DocOps Agent", page_icon="📚", layout="wide")

if UI_PASSWORD:
    if len(UI_PASSWORD) < 16:
        st.error("DOCOPS_UI_PASSWORD 必须至少包含 16 个字符。")
        st.stop()
    if not st.session_state.get("ui_authenticated", False):
        st.title("DocOps Agent 登录")
        with st.form("ui-login"):
            supplied_password = st.text_input("访问口令", type="password")
            submitted = st.form_submit_button("登录", use_container_width=True)
        if submitted:
            if compare_digest(supplied_password, UI_PASSWORD):
                st.session_state["ui_authenticated"] = True
                st.rerun()
            else:
                st.error("访问口令错误。")
        st.stop()

st.title("DocOps Agent")
st.caption("可信企业知识问答 · 原文引用 · 无依据拒答 · 工单人工审批")

with st.sidebar:
    if UI_PASSWORD and st.button("退出登录", use_container_width=True):
        st.session_state["ui_authenticated"] = False
        st.rerun()
    if UI_PASSWORD:
        st.divider()
    st.subheader("添加企业文档")
    upload = st.file_uploader("支持 TXT / Markdown / CSV / 文本型 PDF")
    if upload and st.button("建立索引", use_container_width=True):
        result = _post_json(
            "/documents/upload",
            files={"file": (upload.name, upload.getvalue())},
        )
        if result is not None:
            st.success(f"已建立 {result['chunks']} 个文本块")
            _load_documents()

    st.divider()
    st.subheader("文档管理")
    if st.button("刷新文档列表", use_container_width=True):
        _load_documents()
    for document in st.session_state.get("documents", []):
        st.markdown(f"**{document['title']}**")
        st.caption(
            f"ID: {document['document_id']} · {document['chunks']} 块 · {document['pages']} 页"
        )
        reindex_column, delete_column = st.columns(2)
        if reindex_column.button(
            "重新索引",
            key=f"reindex-{document['document_id']}",
            use_container_width=True,
        ):
            result = _post_json(f"/documents/{document['document_id']}/reindex")
            if result is not None:
                st.success(f"已重新建立 {result['chunks']} 个文本块")
                _load_documents()
        if delete_column.button(
            "删除",
            key=f"delete-{document['document_id']}",
            use_container_width=True,
        ):
            st.session_state["pending_delete_document"] = document
            st.rerun()

    pending_delete = st.session_state.get("pending_delete_document")
    if pending_delete:
        st.warning(f"确认删除“{pending_delete['title']}”？该操作会删除持久化原文和索引。")
        confirm_column, cancel_column = st.columns(2)
        if confirm_column.button("确认删除", type="primary", use_container_width=True):
            result = _request_json(
                "DELETE",
                f"/documents/{pending_delete['document_id']}",
            )
            if result is not None:
                st.session_state["pending_delete_document"] = None
                _load_documents()
                st.rerun()
        if cancel_column.button("取消删除", use_container_width=True):
            st.session_state["pending_delete_document"] = None
            st.rerun()

    st.divider()
    st.markdown("**演示问题**")
    st.code("试用期员工有多少天年假？")
    st.code("报销申请最晚什么时候提交？")
    st.code("创建工单：办公电脑无法开机")

history = st.session_state.setdefault("chat_history", [])
for entry in history:
    with st.chat_message(entry["role"]):
        if entry["role"] == "assistant":
            _render_result(entry["result"])
        else:
            st.write(entry["content"])

pending_approval = st.session_state.get("pending_approval")
if pending_approval:
    st.caption(f"审批将在 {pending_approval['expires_at']} 过期")
    approve_column, cancel_column = st.columns(2)
    if approve_column.button("确认创建工单", type="primary", use_container_width=True):
        approved = _post_json(f"/approvals/{pending_approval['id']}/approve")
        if approved is not None:
            history.append({"role": "assistant", "result": approved})
            st.session_state["pending_approval"] = None
            st.rerun()
    if cancel_column.button("取消", use_container_width=True):
        rejected = _post_json(f"/approvals/{pending_approval['id']}/reject")
        if rejected is not None:
            history.append({"role": "assistant", "result": rejected})
            st.session_state["pending_approval"] = None
            st.rerun()

message = st.chat_input("询问制度，或输入“创建工单：……”")
if message:
    history.append({"role": "user", "content": message})
    result = _post_json(
        "/agent/run",
        json={"message": message},
    )
    if result is not None:
        history.append({"role": "assistant", "result": result})
        if result.get("requires_approval"):
            st.session_state["pending_approval"] = result["approval"]
        st.rerun()
