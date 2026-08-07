from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from docops_agent.bootstrap import build_agent  # noqa: E402


def evaluate(dataset_path: Path) -> dict[str, float | int]:
    agent, _ = build_agent()
    lines = dataset_path.read_text(encoding="utf-8").splitlines()
    examples = [json.loads(line) for line in lines if line]
    keyword_correct = 0
    abstention_correct = 0
    source_hit = 0

    for example in examples:
        answer = agent.rag.answer(example["question"])
        keywords = example.get("answer_keywords", [])
        keyword_correct += int(all(keyword in answer.content for keyword in keywords))
        abstention_correct += int(answer.abstained == example.get("should_abstain", False))
        expected_source = example.get("expected_source")
        source_hit += int(
            expected_source is None
            or any(citation.document_id == expected_source for citation in answer.citations)
        )

    total = max(len(examples), 1)
    return {
        "examples": len(examples),
        "keyword_accuracy": round(keyword_correct / total, 4),
        "abstention_accuracy": round(abstention_correct / total, 4),
        "source_recall_at_k": round(source_hit / total, 4),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate DocOps Agent on a JSONL dataset")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data" / "eval.jsonl")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset), ensure_ascii=False, indent=2))
