"""User-facing exceptions for Driver Signal."""

from __future__ import annotations


class DataProblem(ValueError):
    """A data or configuration issue that a user can act on."""


MEMORY_MESSAGE = (
    "There is not enough memory on this computer for this file or step. Close other programs, keep only the columns "
    "you need, or split the respondents into waves."
)


def friendly_message(exc: Exception) -> str:
    """Return a useful message without exposing implementation details."""
    if isinstance(exc, DataProblem):
        return str(exc)
    if isinstance(exc, MemoryError):
        return MEMORY_MESSAGE
    if isinstance(exc, ValueError):
        return str(exc) or "The selected values could not be analyzed."
    return "Driver Signal could not finish this analysis. Check the selected columns and try again."
