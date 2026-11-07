"""Domain errors. Each maps to a clear HTTP response; none trigger a silent mock fallback."""
from __future__ import annotations


class TripAuraError(Exception):
    status_code = 400
    code = "tripaura_error"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderNotConfiguredError(TripAuraError):
    """Live mode was requested but credentials for an external provider are missing."""
    status_code = 503
    code = "provider_not_configured"


class ProviderRequestError(TripAuraError):
    """An external provider (e.g. Google) returned an error or could not be reached."""
    status_code = 502
    code = "provider_request_failed"


class LocationNotFoundError(TripAuraError):
    status_code = 422
    code = "location_not_found"


class UnsupportedInMockModeError(TripAuraError):
    status_code = 422
    code = "unsupported_in_mock_mode"


class NotFoundError(TripAuraError):
    status_code = 404
    code = "not_found"
