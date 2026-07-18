# neverland-cli

[![PyPI](https://img.shields.io/pypi/v/neverland-cli)](https://pypi.org/project/neverland-cli/)
![Python](https://img.shields.io/pypi/pyversions/neverland-cli)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-2a6db2)](https://mypy-lang.org/)

The `todo` command: a minimalist CLI to manage todos the **GTD** way, built for
fast daily use (fzf/gum for every interaction) and synchronized across devices
through a dedicated git repository. Part of
[neverland](https://github.com/walcark/neverland).

> *Growing up means remembering deadlines. Neverland remembers them for you.*

## Install

```sh
pipx install neverland-cli        # pulls neverland-core on its own
```

`fzf` is required (list selection); `gum` is optional (nicer prompts, falls back
to plain input when absent).

## Quick start

```sh
todo init ~/todo-data        # create/point at the git data repo
todo add "Call the plumber"  # capture into the inbox, zero decisions
todo clarify                 # empty the inbox, one item at a time
todo next -c @computer       # pick the next actions for a context
```

The command surface follows GTD's five steps (capture, clarify, organize,
reflect, engage). See the [main README](https://github.com/walcark/neverland)
for the full workflow and the [domain model](https://github.com/walcark/neverland/blob/main/docs/model.md).
