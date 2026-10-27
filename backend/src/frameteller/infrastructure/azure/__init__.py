"""Azure adapters: Blob Storage for media, project documents and the spend ledger."""

from frameteller.infrastructure.azure.blob import (
    AzureBlobMediaStorage,
    BlobProjectRepository,
    BlobSpendLedger,
    blob_service,
)

__all__ = ["AzureBlobMediaStorage", "BlobProjectRepository", "BlobSpendLedger", "blob_service"]
