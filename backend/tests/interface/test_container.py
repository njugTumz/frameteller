"""The composition root picks storage adapters from STORAGE_BACKEND. Building clients makes no network calls."""

from collections.abc import Callable

from frameteller.infrastructure.azure import AzureBlobMediaStorage
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.interface.container import build_container


def test_local_storage_by_default(make_settings: Callable[..., Settings]) -> None:
    assert isinstance(build_container(make_settings()).storage, LocalFileMediaStorage)


def test_blob_storage_when_configured(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(storage_backend="blob", azure_storage_account="stframetellerstg")
    assert isinstance(build_container(settings).storage, AzureBlobMediaStorage)
