import pytest


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """Deterministic git identity for commits created in tests."""
    for var, val in {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(var, val)
