from __future__ import annotations

import re

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")
HAN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
COMMON_TOKENS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "或",
    "及",
    "为",
    "有",
    "能",
    "可",
    "会",
    "应",
    "个",
    "一",
    "人",
    "日",
    "天",
    "时",
    "什",
    "么",
    "哪",
    "吗",
    "呢",
    "公",
    "司",
    "什么",
    "多少",
    "怎么",
    "时候",
    "哪一",
    "一天",
    "公司",
}


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text without third-party dependencies."""
    normalized = text.lower()
    tokens = TOKEN_PATTERN.findall(normalized)
    for run in HAN_PATTERN.findall(normalized):
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return [token for token in tokens if token not in COMMON_TOKENS]


def character_ngrams(text: str, n: int = 3) -> set[str]:
    compact = re.sub(r"\s+", "", text.lower())
    if len(compact) <= n:
        return {compact} if compact else set()
    return {compact[index : index + n] for index in range(len(compact) - n + 1)}
