"""Error types. Messages are written for end users: no paths, no tracebacks."""
from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """A failure inside the engine/jobs layer with a user-safe message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ApiError(Exception):
    """An error that maps directly to an HTTP response."""

    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
