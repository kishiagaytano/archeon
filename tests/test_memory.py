"""Tests for the Cognee memory wrapper that do not require cognee itself."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from archeon import memory
from archeon.schema import SourceRecord, SourceType


def test_source_record_gets_typed_header() -> None:
    record = SourceRecord(
        source=SourceType.COMMIT,
        content="replace redis with postgres",
        metadata={"sha": "9f64b1c", "author": "Owen Brooks"},
    )
    text = memory._to_text(record)
    assert text.startswith("[source=commit]")
    assert "[sha=9f64b1c]" in text
    assert "[author=Owen Brooks]" in text
    assert "replace redis with postgres" in text


def test_plain_string_passes_through() -> None:
    assert memory._to_text("hello") == "hello"


def test_unavailable_cognee_raises_helpful_error() -> None:
    if memory.cognee_available():
        pytest.skip("cognee is installed; graceful-degradation path not exercised")
    with pytest.raises(memory.CogneeUnavailableError):
        memory.remember_sync(["anything"])


def test_capabilities_detect_available_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_memify(*, signal=None, **kwargs):
        return None

    fake_cognee = SimpleNamespace(
        add=lambda *args, **kwargs: None,
        search=lambda *args, **kwargs: None,
        cognify=lambda *args, **kwargs: None,
        memify=fake_memify,
        prune=SimpleNamespace(prune_data=lambda: None, delete=lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(memory, "cognee", fake_cognee, raising=False)

    caps = memory.capabilities()

    assert caps.available is True
    assert caps.add_api is True
    assert caps.search_api is True
    assert caps.cognify_api is True
    assert caps.forget_api == "prune.delete"
    assert caps.improve_api == "memify"


def test_cloud_config_reads_supported_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COGNEE_BASE_URL", "https://tenant.aws.cognee.ai")
    monkeypatch.setenv("COGNEE_API_KEY", "cloud-key")

    config = memory.cloud_config()

    assert config is not None
    assert config.base_url == "https://tenant.aws.cognee.ai"
    assert config.api_key == "cloud-key"


def test_remember_with_receipts_preserves_ids_and_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCognee:
        async def add(self, texts, dataset_name):
            assert dataset_name == memory.DEFAULT_DATASET
            assert len(texts) == 1
            return [{"id": "chunk-123"}]

        async def cognify(self):
            raise AssertionError("cognify() should not run in this test")

    monkeypatch.setattr(memory, "cognee", FakeCognee(), raising=False)
    record = SourceRecord(
        source=SourceType.COMMIT,
        content="replace redis with postgres",
        metadata={
            "locator": "src/atlas_api/storage.py",
            "files": ["src/atlas_api/storage.py", "src/atlas_api/sessions.py"],
        },
    )

    receipts = memory.remember_with_receipts_sync([record], cognify=False)

    assert len(receipts) == 1
    assert receipts[0].memory_id == "chunk-123"
    assert receipts[0].locator == "src/atlas_api/storage.py"
    assert receipts[0].file_paths == (
        "src/atlas_api/storage.py",
        "src/atlas_api/sessions.py",
    )


def test_remember_with_receipts_connects_to_cloud_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCognee:
        def __init__(self) -> None:
            self.serve_calls: list[tuple[str, str]] = []

        async def serve(self, url, api_key):
            self.serve_calls.append((url, api_key))

        async def add(self, texts, dataset_name):
            return [{"id": "chunk-123"} for _ in texts]

        async def cognify(self):
            return None

    fake_cognee = FakeCognee()
    monkeypatch.setattr(memory, "cognee", fake_cognee, raising=False)
    monkeypatch.setattr(memory, "_CONNECTED_CLOUD_CONTEXT", None, raising=False)
    monkeypatch.setenv("COGNEE_BASE_URL", "https://tenant.aws.cognee.ai")
    monkeypatch.setenv("COGNEE_API_KEY", "cloud-key")

    receipts = memory.remember_with_receipts_sync(["hello"], cognify=False)

    assert len(receipts) == 1
    assert fake_cognee.serve_calls == [("https://tenant.aws.cognee.ai", "cloud-key")]


def test_remember_with_receipts_accepts_cloud_dict_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCognee:
        async def serve(self, url, api_key):
            return None

        async def remember(self, data, dataset_name):
            assert dataset_name == memory.DEFAULT_DATASET
            return {"items": [{"id": "cloud-123"}]}

    monkeypatch.setattr(memory, "cognee", FakeCognee(), raising=False)
    monkeypatch.setattr(memory, "_CONNECTED_CLOUD_CONTEXT", None, raising=False)
    monkeypatch.setenv("COGNEE_BASE_URL", "https://tenant.aws.cognee.ai")
    monkeypatch.setenv("COGNEE_API_KEY", "cloud-key")

    receipts = memory.remember_with_receipts_sync(["hello"])

    assert len(receipts) == 1
    assert receipts[0].memory_id == "cloud-123"
