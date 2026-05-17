from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda

from app.llm.prompts import PromptConfig, default_rag_prompt
from app.llm.provider import LLMProvider
from app.retrieval.retriever import BaseRetriever


def build_langchain_prompt_template(prompt_config: PromptConfig | None = None) -> PromptTemplate:
    config = prompt_config or default_rag_prompt()
    return PromptTemplate(
        input_variables=["context", "question"],
        template=(
            f"{config.system_prompt}\n"
            f"{config.citation_instruction}\n"
            f"{config.safety_instruction}\n"
            f"{config.format_instruction}\n\n"
            "Context:\n{context}\n\nQuestion: {question}\nAnswer:"
        ),
    )


class LangChainRetrieverWrapper:
    """LangChain Runnable-compatible adapter over the project's retriever contract."""

    def __init__(self, retriever: BaseRetriever) -> None:
        self.retriever = retriever

    def invoke(self, query: str, config: dict[str, Any] | None = None) -> list[Document]:
        result = self.retriever.retrieve(query)
        return [
            Document(
                page_content=str(chunk.get("text", "")),
                metadata={
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "source": chunk.get("source"),
                    "score": chunk.get("score"),
                    **(chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}),
                },
            )
            for chunk in result.chunks
        ]


def _documents_to_context(documents: list[Document]) -> str:
    return "\n\n".join(
        f"[{doc.metadata.get('chunk_id')}] {doc.page_content}"
        for doc in documents
    )


def build_langchain_rag_sequence(
    retriever: BaseRetriever,
    provider: LLMProvider,
    prompt_config: PromptConfig | None = None,
) -> Runnable:
    prompt_template = build_langchain_prompt_template(prompt_config)
    retriever_wrapper = LangChainRetrieverWrapper(retriever)

    def retrieve_step(inputs: dict[str, Any]) -> dict[str, Any]:
        question = str(inputs["question"])
        documents = retriever_wrapper.invoke(question)
        return {"question": question, "documents": documents, "context": _documents_to_context(documents)}

    def prompt_step(inputs: dict[str, Any]) -> dict[str, Any]:
        prompt = prompt_template.format(context=inputs["context"], question=inputs["question"])
        chunks = [
            {
                "chunk_id": str(document.metadata.get("chunk_id")),
                "document_id": str(document.metadata.get("document_id")),
                "text": document.page_content,
                "source": str(document.metadata.get("source")),
                "score": float(document.metadata.get("score") or 0.0),
                "metadata": document.metadata,
            }
            for document in inputs["documents"]
        ]
        return {"question": inputs["question"], "prompt": prompt, "chunks": chunks}

    def generation_step(inputs: dict[str, Any]) -> dict[str, Any]:
        result = provider.generate(inputs["prompt"], inputs["chunks"], inputs["question"])
        return {
            "answer": result.raw_answer,
            "model_name": result.model_name,
            "model_version": result.model_version,
            "finish_reason": result.finish_reason,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "chunks": inputs["chunks"],
        }

    return RunnableLambda(retrieve_step) | RunnableLambda(prompt_step) | RunnableLambda(generation_step)
