from pathlib import Path

import yaml


def load_compose() -> dict:
    return yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))


def test_milvus_profile_services_are_declared_as_optional_extensions() -> None:
    compose = load_compose()
    services = compose["services"]

    assert services["milvus"]["profiles"] == ["milvus"]
    assert services["milvus-etcd"]["profiles"] == ["milvus"]
    assert services["milvus-minio"]["profiles"] == ["milvus"]
    assert services["milvus"]["ports"] == ["19530:19530", "9091:9091"]
    assert "milvus_data" in compose["volumes"]
    assert "milvus_etcd" in compose["volumes"]
    assert "milvus_minio" in compose["volumes"]


def test_langfuse_profile_services_are_declared_as_optional_extensions() -> None:
    compose = load_compose()
    services = compose["services"]

    assert services["langfuse"]["profiles"] == ["langfuse"]
    assert services["langfuse-postgres"]["profiles"] == ["langfuse"]
    assert services["langfuse"]["ports"] == ["3010:3000"]
    assert services["langfuse"]["environment"]["DATABASE_URL"] == (
        "postgresql://langfuse:langfuse@langfuse-postgres:5432/langfuse"
    )
    assert "langfuse_postgres" in compose["volumes"]
