from langchain_core.documents import Document

from app.llm.langchain_rag import LangChainRetrieverWrapper, build_langchain_prompt_template, build_langchain_rag_sequence
from app.llm.provider import LocalMockProvider
from app.retrieval.retriever import FileBackedRetriever


def test_langchain_prompt_template_and_retriever_wrapper() -> None:
    prompt = build_langchain_prompt_template()
    retriever = LangChainRetrieverWrapper(FileBackedRetriever("datasets/samples/rag_documents_extended_v2.jsonl", top_k=1))

    documents = retriever.invoke("What is the return policy?")
    rendered_prompt = prompt.format(context="ctx", question="question")

    assert documents
    assert isinstance(documents[0], Document)
    assert documents[0].metadata["document_id"] == "doc-001"
    assert "Context:\nctx" in rendered_prompt
    assert "Question: question" in rendered_prompt


def test_langchain_rag_sequence_runs_with_current_internal_pipeline_components() -> None:
    retriever = FileBackedRetriever("datasets/samples/rag_documents_extended_v2.jsonl", top_k=1)
    provider = LocalMockProvider("mock:langchain-test")
    chain = build_langchain_rag_sequence(retriever, provider)

    result = chain.invoke({"question": "What is the return policy?"})

    assert "Sources:" in result["answer"]
    assert result["model_name"] == "mock:langchain-test"
    assert result["model_version"] == "mock-v1"
    assert result["finish_reason"] == "stop"
    assert result["chunks"][0]["document_id"] == "doc-001"
