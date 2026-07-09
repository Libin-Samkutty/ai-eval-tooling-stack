"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _vertex_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure VERTEX_PROJECT_ID is set before any test imports src.chatbot.main.

    main.py's module-level `config = load_config()` reads this env var and
    raises KeyError if it's unset, which would otherwise break every test
    that imports the app in a clean environment (e.g. CI).
    """
    monkeypatch.setenv("VERTEX_PROJECT_ID", "test-project")
