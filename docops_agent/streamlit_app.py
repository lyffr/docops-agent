from __future__ import annotations

import os

import requests
import streamlit as st

API_URL = os.getenv("DOCOPS_API_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="DocOps Agent", page_icon="📚", layout="wide")
st.title("DocOps Agent")
st.caption("可信企业知识问答 · 原文引用 · 无依据拒答 · 工单人工审批")

with st.sidebar:
    st.subheader("添加企业文档")
    upload = st.file_uploader("支持 TXT / Markdown / CSV / 文本型 PDF")
    if upload and st.button("建立索引", use_container_width=True):
        response = requests.post(
            f"{API_URL}/documents/upload",
            files={"file": (upload.name, upload.getvalue())},
            timeout=60,
        )
        if response.ok:
            st.success(f"已建立 {response.json()['chunks']} 个文本块")
        else:
            st.error(response.text)

    st.divider()
    st.markdown("**演示问题**")
    st.code("试用期员工有多少天年假？")
    st.code("报销申请最晚什么时候提交？")
    st.code("创建工单：办公电脑无法开机")

message = st.chat_input("询问制度，或输入“创建工单：……”")
if message:
    with st.chat_message("user"):
        st.write(message)
    with st.chat_message("assistant"):
        response = requests.post(
            f"{API_URL}/agent/run",
            json={"message": message, "approved": False},
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        st.write(result["message"])

        if result.get("requires_approval"):
            if st.button("确认创建工单"):
                approved = requests.post(
                    f"{API_URL}/agent/run",
                    json={"message": message, "approved": True},
                    timeout=60,
                ).json()
                st.success(approved["message"])

        answer = result.get("answer")
        if answer:
            st.caption(f"置信度：{answer['confidence']:.2f}")
            for index, citation in enumerate(answer.get("citations", []), start=1):
                page = citation.get("page") or "?"
                with st.expander(f"[{index}] {citation['title']} · 第 {page} 页"):
                    st.write(citation["quote"])

