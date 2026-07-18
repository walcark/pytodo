"""pytodo core: the UI-agnostic domain model, storage and git sync.

See ``docs/model.md`` for the domain. This package knows nothing about the CLI
or any other frontend; the layering is enforced by ``test_layering`` and a ruff
banned-import rule.
"""
