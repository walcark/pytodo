# neverland-core

[![PyPI](https://img.shields.io/pypi/v/neverland-core)](https://pypi.org/project/neverland-core/)
![Python](https://img.shields.io/pypi/pyversions/neverland-core)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-2a6db2)](https://mypy-lang.org/)

The domain core of [neverland](https://github.com/walcark/neverland), a GTD todo
manager. This package is UI-agnostic: the model, the file storage, and the git
sync live here, with no CLI or web dependency. It is the foundation the
`neverland-cli` and `neverland-server` distributions build on.

> *Growing up means remembering deadlines. Neverland remembers them for you.*

## Install

```sh
pip install neverland-core
```

You usually do not install it directly: `neverland-cli` and `neverland-server`
depend on it and pull it in on their own.

## What it provides

- The GTD domain model (todos, projects, states, area/context vocabulary).
- One-markdown-file-per-todo storage in a dedicated git data repository.
- Instant local commits with best-effort background pull/push.

The reasoning behind the model is documented in
[`docs/model.md`](https://github.com/walcark/neverland/blob/main/docs/model.md).
See the [main README](https://github.com/walcark/neverland) for the full guide.
