"""Interface implementations."""

from code_assistant.interfaces.cli import cli, main
from code_assistant.interfaces.web import app

__all__ = ["cli", "main", "app"]