from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

API_URL = os.getenv("DOCOPS_API_URL", "http://localhost:8000").rstrip("/")


def _post_json(path: str, **kwargs: Any) -> dict[str, Any] | None:
    try:
        response = requests.post(f"{API_URL}{path}", timeout=60, **kwargs)
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
    if not isinstance(payload, dict):
        st.error("DocOps API 返回了无法识别的响应。")
        return None
    return payload


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
st.title("DocOps Agent")
st.caption("可信企业知识问答 · 原文引用 · 无依据拒答 · 工单人工审批")

with st.sidebar:
    st.subheader("添加企业文档")
    upload = st.file_uploader("支持 TXT / Markdown / CSV / 文本型 PDF")
    if upload and st.button("建立索引", use_container_width=True):
        result = _post_json(
            "/documents/upload",
            files={"file": (upload.name, upload.getvalue())},
        )
        if result is not None:
            st.success(f"已建立 {result['chunks']} 个文本块")

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

pending_message = st.session_state.get("pending_ticket_message")
if pending_message:
    approve_column, cancel_column = st.columns(2)
    if approve_column.button("确认创建工单", type="primary", use_container_width=True):
        approved = _post_json(
            "/agent/run",
            json={"message": pending_message, "approved": True},
        )
        if approved is not None:
            history.append({"role": "assistant", "result": approved})
            st.session_state["pending_ticket_message"] = None
            st.rerun()
    if cancel_column.button("取消", use_container_width=True):
        st.session_state["pending_ticket_message"] = None
        st.rerun()

message = st.chat_input("询问制度，或输入“创建工单：……”")
if message:
    history.append({"role": "user", "content": message})
    result = _post_json(
        "/agent/run",
        json={"message": message, "approved": False},
    )
    if result is not None:
        history.append({"role": "assistant", "result": result})
        if result.get("requires_approval"):
            st.session_state["pending_ticket_message"] = message
        st.rerun()
