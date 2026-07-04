"""Cognee-backed memory layer for Archeon.

This module is the single place Archeon talks to Cognee. It exposes an
Archeon-flavored API -- :func:`remember`, :func:`recall`, and lifecycle helpers
-- on top of Cognee's primitives so the rest of the codebase never imports
``cognee`` directly.

Design notes
    * Cognee is optional at import time. If it is not installed, this module
      still imports and :func:`cognee_available` returns ``False``; the CLI can
      then print a friendly message instead of crashing.
    * Cognee's API is async. We expose async coroutines plus thin ``*_sync``
      wrappers that call :func:`asyncio.run` for CLI and test convenience.
    * ``remember`` accepts either raw strings or :class:`~archeon.schema.SourceRecord`
      objects and can preserve stable ids returned by ``cognee.add`` when the
      backend provides them.
    * Lifecycle capability discovery lives here so the provider, smoke test,
      and demo all report the same backend truth.

Configuration (environment variables)
    ARCHEON_DATASET   Cognee dataset name to read/write. Default ``"archeon"``.
    COGNEE_BASE_URL   Optional Cognee Cloud tenant URL. When paired with
                      ``COGNEE_API_KEY``, Archeon routes memory operations to
                      Cognee Cloud via ``cognee.serve()``.
    COGNEE_API_KEY    Optional Cognee Cloud API key used with
                      ``COGNEE_BASE_URL`` for managed Cloud billing/runtime.
    LLM_API_KEY       Passed through to Cognee for cognify/search. Required for
                      direct-provider local mode; without it, local
                      ``cognify``/search will surface Cognee's own error.
"""

from __future__ import annotations

import atexit
import asyncio
import inspect
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Optional, Union
from uuid import UUID

from .schema import SourceRecord

try:  # Cognee is a heavy, optional dependency.
    import cognee  # type: ignore

    _COGNEE_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - exercised only without cognee
    cognee = None  # type: ignore
    _COGNEE_IMPORT_ERROR = exc


DEFAULT_DATASET = os.environ.get("ARCHEON_DATASET", "archeon")

# Cognee defaults its databases to a path inside site-packages that is already
# ~90 chars deep; LanceDB then nests long UUID folders/files under it and blows
# past the Windows 260-char MAX_PATH limit (os error 3 on write). Relocate the
# store to a short directory so the full paths stay well under the limit.
# Override with ARCHEON_COGNEE_HOME.
COGNEE_HOME = os.environ.get(
    "ARCHEON_COGNEE_HOME", os.path.join(os.path.expanduser("~"), ".acg")
)

Rememberable = Union[str, SourceRecord]

_COGNEE_PATHS_CONFIGURED = False


def _configure_cognee_paths() -> None:
    """Point cognee's system/data directories at a short path (once)."""
    global _COGNEE_PATHS_CONFIGURED
    if cognee is None or _COGNEE_PATHS_CONFIGURED:
        return
    try:
        cognee.config.system_root_directory(os.path.join(COGNEE_HOME, "sys"))
        cognee.config.data_root_directory(os.path.join(COGNEE_HOME, "data"))
    except Exception:  # pragma: no cover - config API drift shouldn't be fatal
        pass
    _COGNEE_PATHS_CONFIGURED = True


@dataclass(frozen=True)
class CogneeCapabilities:
    """Runtime view of which Cognee APIs are available."""

    available: bool
    add_api: bool
    search_api: bool
    cognify_api: bool
    prune_api: bool
    forget_api: str | None = None
    improve_api: str | None = None

    @property
    def supports_forget(self) -> bool:
        return self.forget_api is not None

    @property
    def supports_improve(self) -> bool:
        return self.improve_api is not None


@dataclass(frozen=True)
class RememberReceipt:
    """Best-effort stable handle captured from a ``remember`` call."""

    item_index: int
    text: str
    memory_id: str | None
    source: str | None
    locator: str | None
    file_paths: tuple[str, ...]


@dataclass(frozen=True)
class CogneeCloudConfig:
    """Cloud tenant settings used to route SDK calls to Cognee Cloud."""

    base_url: str
    api_key: str


class CogneeUnavailableError(RuntimeError):
    """Raised when a Cognee-backed operation is attempted without Cognee installed."""


_CONNECTED_CLOUD_CONTEXT: tuple[str, int] | None = None
_SYNC_RUNNER: asyncio.Runner | None = None


def cognee_available() -> bool:
    """Return ``True`` if the ``cognee`` package imported successfully."""
    return cognee is not None


def import_error() -> Optional[Exception]:
    """Return the exception raised while importing cognee, if any."""
    return _COGNEE_IMPORT_ERROR


def _require_cognee() -> None:
    if cognee is None:
        raise CogneeUnavailableError(
            "cognee is not installed or failed to import. Install it with "
            "`pip install -e .[cognee]` (see SCHEMA.md / README). "
            f"Original import error: {_COGNEE_IMPORT_ERROR!r}"
        )
    _configure_cognee_paths()


def cloud_config() -> CogneeCloudConfig | None:
    """Return Cognee Cloud settings when the environment is configured for it."""
    base_url = os.environ.get("COGNEE_BASE_URL") or os.environ.get("COGNEE_CLOUD_URL")
    api_key = os.environ.get("COGNEE_API_KEY") or os.environ.get("COGNEE_CLOUD_API_KEY")
    if not base_url or not api_key:
        return None
    return CogneeCloudConfig(base_url=base_url, api_key=api_key)


async def _ensure_cloud_connection() -> None:
    """Connect the Cognee SDK to a Cloud tenant when Cloud env vars are present."""
    _require_cognee()
    config = cloud_config()
    if config is None:
        return

    loop_id = id(asyncio.get_running_loop())
    global _CONNECTED_CLOUD_CONTEXT
    if _CONNECTED_CLOUD_CONTEXT == (config.base_url, loop_id):
        return

    serve_fn = getattr(cognee, "serve", None)
    if not callable(serve_fn):
        raise CogneeUnavailableError(
            "Cognee Cloud is configured but this cognee runtime does not expose serve()."
        )

    await _call_maybe_async(serve_fn, url=config.base_url, api_key=config.api_key)
    _CONNECTED_CLOUD_CONTEXT = (config.base_url, loop_id)


def _close_sync_runner() -> None:
    """Close the shared sync runner and remote client, if they were created."""
    global _SYNC_RUNNER, _CONNECTED_CLOUD_CONTEXT
    if _SYNC_RUNNER is None:
        return

    disconnect_fn = getattr(cognee, "disconnect", None)
    if callable(disconnect_fn):
        try:
            _SYNC_RUNNER.run(disconnect_fn())
        except Exception:
            pass

    _SYNC_RUNNER.close()
    _SYNC_RUNNER = None
    _CONNECTED_CLOUD_CONTEXT = None


def _get_sync_runner() -> asyncio.Runner:
    """Return the shared runner used for sync Cloud calls."""
    global _SYNC_RUNNER
    if _SYNC_RUNNER is None:
        _SYNC_RUNNER = asyncio.Runner()
        atexit.register(_close_sync_runner)
    return _SYNC_RUNNER


def _run_sync(coro: Any) -> Any:
    """Run a coroutine, reusing a persistent loop when Cloud mode is enabled."""
    if cloud_config() is not None:
        return _get_sync_runner().run(coro)
    return asyncio.run(coro)


def capabilities() -> CogneeCapabilities:
    """Report which Cognee APIs are available in this runtime."""
    if cognee is None:
        return CogneeCapabilities(
            available=False,
            add_api=False,
            search_api=False,
            cognify_api=False,
            prune_api=False,
        )

    prune = getattr(cognee, "prune", None)
    forget_api = None
    if callable(getattr(cognee, "forget", None)):
        forget_api = "forget"
    elif callable(getattr(prune, "delete", None)) if prune else False:
        forget_api = "prune.delete"

    improve_api = None
    for name in ("improve", "memify"):
        fn = getattr(cognee, name, None)
        if callable(fn) and _supports_node_feedback(fn):
            improve_api = name
            break

    return CogneeCapabilities(
        available=True,
        add_api=callable(getattr(cognee, "add", None)),
        search_api=callable(getattr(cognee, "search", None)),
        cognify_api=callable(getattr(cognee, "cognify", None)),
        prune_api=callable(getattr(prune, "prune_data", None)) if prune else False,
        forget_api=forget_api,
        improve_api=improve_api,
    )


def _to_text(item: Rememberable) -> str:
    """Normalize a rememberable item to the text Cognee should embed."""
    if isinstance(item, SourceRecord):
        source = item.source.value if hasattr(item.source, "value") else str(item.source)
        header_bits = [f"[source={source}]"]
        for key in ("locator", "sha", "pr", "author", "date", "timestamp"):
            value = item.metadata.get(key)
            if value:
                header_bits.append(f"[{key}={value}]")
        return f"{' '.join(header_bits)}\n{item.content}"
    return str(item)


def extract_memory_id(result: Any) -> Optional[str]:
    """Best-effort id extraction from a Cognee add/search result."""
    if result is None:
        return None
    if isinstance(result, str):
        marker = "[id="
        if marker in result:
            return result.split(marker, 1)[1].split("]", 1)[0] or None
        return None
    for key in ("id", "node_id", "chunk_id", "uuid"):
        value = getattr(result, key, None)
        if value is None and isinstance(result, dict):
            value = result.get(key)
        if value:
            return str(value)
    text = getattr(result, "text", None)
    if text is None and isinstance(result, dict):
        text = result.get("text")
    if text:
        marker = "[id="
        if marker in str(text):
            return str(text).split(marker, 1)[1].split("]", 1)[0] or None
    return None


async def _call_maybe_async(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a Cognee API that may be synchronous or async."""
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _supports_node_feedback(fn: Any) -> bool:
    """Return True when a function exposes a node-level feedback parameter."""
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return "signal" in signature.parameters or "vote" in signature.parameters


def _coerce_uuid(value: str) -> str | UUID:
    """Return a UUID object when the value looks like one, else the original string."""
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return value


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _looks_like_file_path(value: str) -> bool:
    if "/" in value or "\\" in value:
        return bool(PurePosixPath(value.replace("\\", "/")).suffix)
    suffix = PurePosixPath(value).suffix
    return bool(suffix and suffix != value)


def _candidate_file_paths(item: Rememberable) -> tuple[str, ...]:
    if not isinstance(item, SourceRecord):
        return ()

    metadata = item.metadata
    candidates: list[str] = []
    path_value = metadata.get("path")
    if isinstance(path_value, str) and _looks_like_file_path(path_value):
        candidates.append(path_value)

    locator = metadata.get("locator")
    if isinstance(locator, str) and _looks_like_file_path(locator):
        candidates.append(locator)

    files = metadata.get("files")
    if isinstance(files, list):
        for value in files:
            if isinstance(value, str) and _looks_like_file_path(value):
                candidates.append(value)

    normalized = [_normalize_path(path) for path in candidates]
    return tuple(dict.fromkeys(normalized))


def _extract_receipt_items(raw_result: Any, expected: int) -> list[Any]:
    if expected == 0:
        return []
    if raw_result is None:
        return [None] * expected
    if isinstance(raw_result, (list, tuple)):
        items = list(raw_result)
    elif isinstance(raw_result, dict):
        items = None
        for key in ("items", "results", "data", "ids"):
            value = raw_result.get(key)
            if isinstance(value, (list, tuple)):
                items = list(value)
                break
        if items is None:
            items = [raw_result]
    else:
        items = None
        for attr in ("items", "results", "data", "ids"):
            value = getattr(raw_result, attr, None)
            if isinstance(value, (list, tuple)):
                items = list(value)
                break
        if items is None:
            items = [raw_result]

    if len(items) < expected:
        items.extend([None] * (expected - len(items)))
    return items[:expected]


def _build_receipts(
    items: list[Rememberable],
    texts: list[str],
    add_result: Any,
) -> list[RememberReceipt]:
    result_items = _extract_receipt_items(add_result, len(texts))
    receipts: list[RememberReceipt] = []
    for index, (item, text, result_item) in enumerate(zip(items, texts, result_items)):
        source = None
        locator = None
        if isinstance(item, SourceRecord):
            source = item.source.value if hasattr(item.source, "value") else str(item.source)
            locator_value = item.metadata.get("locator")
            if locator_value:
                locator = str(locator_value)

        receipts.append(
            RememberReceipt(
                item_index=index,
                text=text,
                memory_id=extract_memory_id(result_item),
                source=source,
                locator=locator,
                file_paths=_candidate_file_paths(item),
            )
        )
    return receipts


def _build_receipts_from_remember_result(
    items: list[Rememberable],
    texts: list[str],
    remember_result: Any,
) -> list[RememberReceipt]:
    result_items: list[Any]
    if isinstance(remember_result, dict):
        result_items = list(remember_result.get("items", []) or [])
    else:
        result_items = list(getattr(remember_result, "items", []) or [])
    if len(result_items) < len(texts):
        result_items.extend([None] * (len(texts) - len(result_items)))

    receipts: list[RememberReceipt] = []
    for index, (item, text, result_item) in enumerate(zip(items, texts, result_items)):
        source = None
        locator = None
        if isinstance(item, SourceRecord):
            source = item.source.value if hasattr(item.source, "value") else str(item.source)
            locator_value = item.metadata.get("locator")
            if locator_value:
                locator = str(locator_value)

        memory_id = None
        if isinstance(result_item, dict):
            raw_id = result_item.get("id")
            if raw_id is not None:
                memory_id = str(raw_id)

        receipts.append(
            RememberReceipt(
                item_index=index,
                text=text,
                memory_id=memory_id,
                source=source,
                locator=locator,
                file_paths=_candidate_file_paths(item),
            )
        )
    return receipts


# --------------------------------------------------------------------------- #
# Core async API
# --------------------------------------------------------------------------- #


async def remember_with_receipts(
    items: Iterable[Rememberable],
    *,
    dataset: str = DEFAULT_DATASET,
    cognify: bool = True,
) -> list[RememberReceipt]:
    """Add items to Cognee and preserve any stable ids returned by ``add``."""
    _require_cognee()
    await _ensure_cloud_connection()
    normalized_items = list(items)
    texts = [_to_text(item) for item in normalized_items]
    if not texts:
        return []

    if cloud_config() is not None and callable(getattr(cognee, "remember", None)):
        remember_payload: str | list[str]
        remember_payload = texts[0] if len(texts) == 1 else texts
        remember_result = await cognee.remember(  # type: ignore[union-attr]
            remember_payload,
            dataset_name=dataset,
        )
        return _build_receipts_from_remember_result(
            normalized_items,
            texts,
            remember_result,
        )

    add_result = await cognee.add(texts, dataset_name=dataset)  # type: ignore[union-attr]
    receipts = _build_receipts(normalized_items, texts, add_result)
    if cognify:
        await cognee.cognify()  # type: ignore[union-attr]
    return receipts


async def remember(
    items: Iterable[Rememberable],
    *,
    dataset: str = DEFAULT_DATASET,
    cognify: bool = True,
) -> int:
    """Add items to Cognee and (optionally) build the knowledge graph."""
    receipts = await remember_with_receipts(items, dataset=dataset, cognify=cognify)
    return len(receipts)


async def recall(
    query: str,
    *,
    search_type: Optional[str] = None,
    top_k: int = 10,
) -> list[Any]:
    """Query Cognee's memory and return raw results."""
    _require_cognee()
    await _ensure_cloud_connection()

    if cloud_config() is not None and callable(getattr(cognee, "recall", None)):
        return await cognee.recall(  # type: ignore[union-attr]
            query_text=query,
            datasets=[DEFAULT_DATASET],
            top_k=top_k,
        )

    search_kwargs: dict[str, Any] = {"query_text": query, "top_k": top_k}
    search_type_enum = _resolve_search_type(search_type)
    if search_type_enum is not None:
        search_kwargs["query_type"] = search_type_enum

    try:
        return await cognee.search(**search_kwargs)  # type: ignore[union-attr]
    except TypeError:
        return await cognee.search(query)  # type: ignore[union-attr]


async def forget(node_id: str) -> bool:
    """Forget a single Cognee node/chunk when the runtime supports it."""
    _require_cognee()
    await _ensure_cloud_connection()
    caps = capabilities()
    if caps.forget_api == "forget":
        try:
            forget_fn = getattr(cognee, "forget")
            try:
                await _call_maybe_async(
                    forget_fn,
                    data_id=_coerce_uuid(node_id),
                    dataset=DEFAULT_DATASET,
                )
            except TypeError:
                await _call_maybe_async(forget_fn, node_id)
            return True
        except Exception:  # noqa: BLE001
            return False
    if caps.forget_api == "prune.delete":
        try:
            prune = getattr(cognee, "prune")
            await _call_maybe_async(getattr(prune, "delete"), node_id)
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


async def improve(node_id: str, signal: str) -> bool:
    """Improve/memify a single Cognee node when the runtime supports it."""
    _require_cognee()
    await _ensure_cloud_connection()
    caps = capabilities()
    if caps.improve_api is None:
        return False

    fn = getattr(cognee, caps.improve_api)
    try:
        await _call_maybe_async(fn, node_id, signal=signal)
        return True
    except TypeError:
        try:
            await _call_maybe_async(fn, node_id)
            return True
        except Exception:  # noqa: BLE001
            return False
    except Exception:  # noqa: BLE001
        return False


def _resolve_search_type(name: Optional[str]) -> Any:
    """Resolve a ``SearchType`` enum member by name, tolerating API drift."""
    search_type_cls = getattr(cognee, "SearchType", None)
    if search_type_cls is None:
        return None
    wanted = name or "GRAPH_COMPLETION"
    return getattr(search_type_cls, wanted, None) or getattr(
        search_type_cls, "GRAPH_COMPLETION", None
    )


async def forget_all(*, dataset: str = DEFAULT_DATASET) -> None:
    """Prune all data/system state from Cognee (used by tests and resets)."""
    _require_cognee()
    await _ensure_cloud_connection()
    prune = getattr(cognee, "prune", None)
    if prune is None:
        raise CogneeUnavailableError("This cognee version does not expose prune().")
    await prune.prune_data()  # type: ignore[union-attr]
    await prune.prune_system(metadata=True)  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Sync convenience wrappers (for the CLI and quick scripts)
# --------------------------------------------------------------------------- #


def remember_sync(
    items: Iterable[Rememberable],
    *,
    dataset: str = DEFAULT_DATASET,
    cognify: bool = True,
) -> int:
    """Synchronous wrapper around :func:`remember`."""
    return _run_sync(remember(items, dataset=dataset, cognify=cognify))


def remember_with_receipts_sync(
    items: Iterable[Rememberable],
    *,
    dataset: str = DEFAULT_DATASET,
    cognify: bool = True,
) -> list[RememberReceipt]:
    """Synchronous wrapper around :func:`remember_with_receipts`."""
    return _run_sync(remember_with_receipts(items, dataset=dataset, cognify=cognify))


def recall_sync(
    query: str,
    *,
    search_type: Optional[str] = None,
    top_k: int = 10,
) -> list[Any]:
    """Synchronous wrapper around :func:`recall`."""
    return _run_sync(recall(query, search_type=search_type, top_k=top_k))


def forget_sync(node_id: str) -> bool:
    """Synchronous wrapper around :func:`forget`."""
    return _run_sync(forget(node_id))


def improve_sync(node_id: str, signal: str) -> bool:
    """Synchronous wrapper around :func:`improve`."""
    return _run_sync(improve(node_id, signal))


__all__ = [
    "CogneeCapabilities",
    "CogneeCloudConfig",
    "CogneeUnavailableError",
    "DEFAULT_DATASET",
    "RememberReceipt",
    "capabilities",
    "cloud_config",
    "cognee_available",
    "extract_memory_id",
    "forget",
    "forget_all",
    "forget_sync",
    "import_error",
    "improve",
    "improve_sync",
    "remember",
    "remember_sync",
    "remember_with_receipts",
    "remember_with_receipts_sync",
    "recall",
    "recall_sync",
]
