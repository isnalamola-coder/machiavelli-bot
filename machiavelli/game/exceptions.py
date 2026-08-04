"""Exceptions raised by the game domain lifecycle."""


class FailedToStartError(Exception):
    """Raised when a game cannot start because prerequisites are missing."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DuplicatedGameException(Exception):
    """Raised when a game name or channel is already registered."""


class GameNotFoundException(Exception):
    """Raised when a requested game does not exist in persistence."""


__all__ = [
    "DuplicatedGameException",
    "FailedToStartError",
    "GameNotFoundException",
]
