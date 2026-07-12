"""Transport-agnostic service errors.

A single exception carrying an HTTP-ish status code keeps the service layer
decoupled from the web framework while letting a lone exception handler in the
web layer translate failures into responses. No per-error subclass hierarchy —
the status code is the discriminator.
"""

from __future__ import annotations


class ServiceError(Exception):
    """A service-layer failure with an HTTP status and client-safe detail."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail

    # ponytail: helpers, not subclasses — keeps callers to one import.
    @classmethod
    def not_found(cls, detail: str) -> "ServiceError":
        return cls(404, detail)

    @classmethod
    def invalid(cls, detail: str) -> "ServiceError":
        return cls(422, detail)

    @classmethod
    def bad_request(cls, detail: str) -> "ServiceError":
        return cls(400, detail)
