from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="llmops-dq-observability", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://dq:dq@localhost:5432/dq_observability",
        alias="DATABASE_URL",
    )
    prometheus_namespace: str = Field(default="dq", alias="PROMETHEUS_NAMESPACE")
    default_data_contour: str = Field(
        default="rag_documents",
        alias="DEFAULT_DATA_CONTOUR",
    )
    default_baseline_strategy: str = Field(
        default="previous_version",
        alias="DEFAULT_BASELINE_STRATEGY",
    )
    hard_gate_enabled: bool = Field(default=True, alias="HARD_GATE_ENABLED")
    soft_gate_enabled: bool = Field(default=True, alias="SOFT_GATE_ENABLED")
    quality_gate_response_window: int = Field(default=50, alias="QUALITY_GATE_RESPONSE_WINDOW")
    llm_judge_enabled: bool = Field(default=False, alias="LLM_JUDGE_ENABLED")
    llm_allow_mock_fallback: bool = Field(default=True, alias="LLM_ALLOW_MOCK_FALLBACK")
    default_model_profile_id: str = Field(default="mock", alias="DEFAULT_MODEL_PROFILE_ID")
    model_profile_qwen_ollama_enabled: bool = Field(default=False, alias="MODEL_PROFILE_QWEN_OLLAMA_ENABLED")
    model_profile_ollama_llama_enabled: bool = Field(default=False, alias="MODEL_PROFILE_OLLAMA_LLAMA_ENABLED")
    mlflow_tracking_uri: str = Field(default="http://localhost:5000", alias="MLFLOW_TRACKING_URI")
    mlflow_enabled: bool = Field(default=False, alias="MLFLOW_ENABLED")
    api_key: str = Field(default="change-me", alias="API_KEY")
    api_key_auth_enabled: bool = Field(default=False, alias="API_KEY_AUTH_ENABLED")
    store_raw_input: bool = Field(default=False, alias="STORE_RAW_INPUT")
    store_raw_output: bool = Field(default=False, alias="STORE_RAW_OUTPUT")
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    local_llm_model: str = Field(default="llama3", alias="LOCAL_LLM_MODEL")
    local_llm_base_url: str = Field(default="http://host.docker.internal:11434", alias="LOCAL_LLM_BASE_URL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    qwen_ollama_model: str = Field(default="qwen2.5:7b", alias="QWEN_OLLAMA_MODEL")
    qwen_ollama_3b_model: str = Field(default="qwen2.5:3b", alias="QWEN_OLLAMA_3B_MODEL")
    qwen_ollama_7b_model: str = Field(default="qwen2.5:7b", alias="QWEN_OLLAMA_7B_MODEL")
    milvus_host: str = Field(default="milvus", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    milvus_collection: str = Field(default="rag_chunks", alias="MILVUS_COLLECTION")
    milvus_enabled: bool = Field(default=False, alias="MILVUS_ENABLED")
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://langfuse:3000", alias="LANGFUSE_HOST")
    langfuse_enabled: bool = Field(default=False, alias="LANGFUSE_ENABLED")
    default_rag_dataset_path: str = Field(
        default="datasets/samples/rag_documents_extended_v2.jsonl",
        alias="DEFAULT_RAG_DATASET_PATH",
    )
    default_rag_dataset_version: str = Field(default="sample-v2", alias="DEFAULT_RAG_DATASET_VERSION")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    rag_min_retrieval_score: float = Field(default=0.0, alias="RAG_MIN_RETRIEVAL_SCORE")
    quality_thresholds_path: str = Field(
        default="config/quality_thresholds.yaml",
        alias="QUALITY_THRESHOLDS_PATH",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
