from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptConfig:
    system_prompt: str
    citation_instruction: str
    safety_instruction: str
    format_instruction: str
    prompt_version: str

    @property
    def prompt_hash(self) -> str:
        payload = "|".join(
            [
                self.system_prompt,
                self.citation_instruction,
                self.safety_instruction,
                self.format_instruction,
                self.prompt_version,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_rag_prompt() -> PromptConfig:
    return PromptConfig(
        system_prompt=(
            "You are a RAG assistant. Use only the provided Context. "
            "Do not answer from general knowledge. Answer in the same language as the user question when possible."
        ),
        citation_instruction=(
            "Cite every source you used. Always include exactly one final Sources: line using "
            "document_id#chunk_id references from the context, for example: "
            "Sources: doc-001#doc-001-chunk-0. If there are no usable sources, write: Sources: none."
        ),
        safety_instruction="Do not reveal sensitive data or invent unavailable facts.",
        format_instruction=(
            "If the Context does not contain enough information to answer, return exactly: "
            "I do not have enough context to answer this question based on the available documents.\n"
            "Sources: none"
        ),
        prompt_version="rag-v2",
    )


def assemble_prompt(query: str, context_chunks: list[dict], prompt_config: PromptConfig) -> str:
    context_text = "\n\n".join(
        f"[{chunk['document_id']}#{chunk['chunk_id']}] {chunk['text']}" for chunk in context_chunks
    )
    return (
        f"{prompt_config.system_prompt}\n"
        f"{prompt_config.citation_instruction}\n"
        f"{prompt_config.safety_instruction}\n"
        f"{prompt_config.format_instruction}\n\n"
        f"Context:\n{context_text}\n\nQuestion: {query}\nAnswer:"
    )
