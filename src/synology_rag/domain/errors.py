"""Typed error hierarchy with stable external codes.

External surfaces (REST/MCP) map these to safe responses. Public messages never
contain SQL, secrets, stack traces, connection strings, or internal file paths;
optional ``internal_detail`` is for logs only and is never returned to clients.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_FILTER = "unsupported_filter"
    UNKNOWN_COLLECTION = "unknown_collection"
    EMBEDDING_INCOMPATIBLE = "embedding_incompatible"
    EMBEDDING_UNAVAILABLE = "embedding_unavailable"
    QDRANT_UNAVAILABLE = "qdrant_unavailable"
    POSTGRES_UNAVAILABLE = "postgres_unavailable"
    DOCUMENT_NOT_FOUND = "document_not_found"
    CHUNK_NOT_FOUND = "chunk_not_found"
    RETRIEVAL_TIMEOUT = "retrieval_timeout"
    CONFIGURATION_ERROR = "configuration_error"
    AUTHENTICATION_FAILED = "authentication_failed"
    INTERNAL_ERROR = "internal_error"


class RetrievalError(Exception):
    """Base class for all retrieval errors.

    Attributes:
        code: stable machine-readable error code.
        message: safe, human-readable message for clients.
        http_status: suggested HTTP status for the REST adapter.
        retryable: whether the caller may reasonably retry.
        internal_detail: extra context for logs only - never returned.
    """

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str, *, internal_detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.internal_detail = internal_detail


class InvalidRequestError(RetrievalError):
    code = ErrorCode.INVALID_REQUEST
    http_status = 400


class UnsupportedFilterError(RetrievalError):
    code = ErrorCode.UNSUPPORTED_FILTER
    http_status = 400


class UnknownCollectionError(RetrievalError):
    code = ErrorCode.UNKNOWN_COLLECTION
    http_status = 400


class EmbeddingIncompatibleError(RetrievalError):
    code = ErrorCode.EMBEDDING_INCOMPATIBLE
    http_status = 500


class EmbeddingUnavailableError(RetrievalError):
    code = ErrorCode.EMBEDDING_UNAVAILABLE
    http_status = 503
    retryable = True


class QdrantUnavailableError(RetrievalError):
    code = ErrorCode.QDRANT_UNAVAILABLE
    http_status = 503
    retryable = True


class PostgresUnavailableError(RetrievalError):
    code = ErrorCode.POSTGRES_UNAVAILABLE
    http_status = 503
    retryable = True


class DocumentNotFoundError(RetrievalError):
    code = ErrorCode.DOCUMENT_NOT_FOUND
    http_status = 404


class ChunkNotFoundError(RetrievalError):
    code = ErrorCode.CHUNK_NOT_FOUND
    http_status = 404


class RetrievalTimeoutError(RetrievalError):
    code = ErrorCode.RETRIEVAL_TIMEOUT
    http_status = 504
    retryable = True


class ConfigurationError(RetrievalError):
    code = ErrorCode.CONFIGURATION_ERROR
    http_status = 500


class AuthenticationError(RetrievalError):
    code = ErrorCode.AUTHENTICATION_FAILED
    http_status = 401
