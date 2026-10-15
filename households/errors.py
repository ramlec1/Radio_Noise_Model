"""Errors raised while loading household locations."""


class ExternalServiceError(Exception):
    """Raised when Overpass fails or times out."""


class LocalDataError(Exception):
    """Raised when the local household dataset cannot be used."""
