"""Tiny FastAPI-shaped demo module for Atlas API."""


def create_app() -> str:
    """Return the selected framework name for fixture scans."""
    return "fastapi"


LEGACY_FRAMEWORK = "flask"
