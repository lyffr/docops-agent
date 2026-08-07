from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from urllib import request

from .models import SearchHit
from .tokenization import tokenize

SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n+")


class Generator(ABC):
    @abstractmethod
    def generate(self, question: str, hits: list[SearchHit]) -> str:
        raise NotImplementedError


class ExtractiveGenerator(Generator):
    """Offline fallback that extracts high-overlap evidence sentences."""

    def generate(self, question: str, hits: list[SearchHit]) -> str:
        query_tokens = set(tokenize(question))
        candidates: list[tuple[float, str, int]] = []
        for citation_index, hit in enumerate(hits, start=1):
            for sentence in SENTENCE_SPLIT.split(hit.chunk.content):
                sentence = sentence.strip()
                if not sentence:
                    continue
                sentence_tokens = set(tokenize(sentence))
                overlap = len(query_tokens & sentence_tokens) / max(len(query_tokens), 1)
                candidates.append((overlap + hit.score * 0.25, sentence, citation_index))
        selected = sorted(candidates, reverse=True)[:2]
        if not selected:
            return "现有文档中没有足够证据回答该问题。"
        return "\n".join(f"{sentence} [{index}]" for _, sentence, index in selected)


class OpenAICompatibleGenerator(Generator):
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 45) -> None:
        if not api_key or not model:
            raise ValueError("OpenAI-compatible provider requires API key and model")
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, question: str, hits: list[SearchHit]) -> str:
        evidence = "\n\n".join(
            f"[{index}] {hit.chunk.title} 第{hit.chunk.page or '?'}页\n{hit.chunk.content}"
            for index, hit in enumerate(hits, start=1)
        )
        system = (
            "你是企业知识助手。只能依据证据回答，每个事实后标注证据编号如[1]。"
            "若证据不足，明确回答不知道，禁止编造。"
        )
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"问题：{question}\n\n证据：\n{evidence}"},
                ],
            }
        ).encode()
        http_request = request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(http_request, timeout=self.timeout) as response:
            result = json.loads(response.read())
        return str(result["choices"][0]["message"]["content"])

