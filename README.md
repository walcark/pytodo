# todo

A minimalist CLI to manage todo lists, built for fast daily use (fzf/gum for
every interaction) and synchronized across devices through a dedicated git
repository. Adding, completing or deleting a todo takes a couple of seconds.

## How it works in one picture

```
your machine                          git remote (e.g. GitHub)
------------                          ------------------------
todo add "..."  --> commit (instant)
                    |
                    +--> [detached background process] pull + push  ---> origin
                                                                          ^
another device: todo sync  <-- pull ------------------------------------ +
```

- **One markdown file per todo** (avoids merge conflicts between devices).
- **Instant local commit**, network sync happens in the background (see
  [Sync model](#sync-model)).

## Requirements

- Python 3.11+
- `git`
- [`fzf`](https://github.com/junegunn/fzf) - **required** (list selection)
- [`gum`](https://github.com/charmbracelet/gum) - *optional* (nicer text input
  and confirmations; falls back to plain prompts when absent)

## Install

```sh
pipx install .
```

This exposes the `todo` command.

## Setup a data repo

The todo *data* lives in its own git repository, separate from this tool. Point
`todo` at it once:

```sh
todo init ~/todo-data          # local path
todo init git@github.com:you/todo-data.git   # or a clone URL
```

`init` creates the layout, sets the repo as active, and remembers its path in
`~/.config/todo/config.toml`. The created repo looks like:

```
todo-data/
├── config.toml     # categories / urgencies / horizons, shared across devices
├── todos/          # active todos, one file per todo
│   └── 20260705-143201-a3f2.md
└── done/           # completed todos (archive)
```

### What happens if the target already exists?

`todo init` (and `todo repo`) are **create-or-validate**:

| Target state                                   | Behaviour                                   |
| ---------------------------------------------- | ------------------------------------------- |
| Path does not exist                            | `mkdir` + `git init` + full scaffold        |
| Existing directory, not a git repo             | `git init` + scaffold the missing parts     |
| Existing git repo, already conformant          | adopted as-is                               |
| Existing git repo with unrelated content only  | asks for confirmation before adding layout  |
| A clone URL                                     | cloned into `~/<repo-name>` then validated  |

> **Note on nested repos.** If the target is a *subdirectory of another git
> repo*, `todo` reuses that enclosing repo. All commits are scoped to the data
> directory (`git add -- .`), so unrelated files are never touched, but a
> `push` will push the whole enclosing repo. Prefer a dedicated repo unless you
> deliberately want todos versioned alongside other content.

### Switch repos

```sh
todo repo                 # print the active data repo
todo repo ~/other-data    # switch to another one (same create-or-validate rules)
```

## Commands

| Command                         | What it does                                                        |
| ------------------------------- | ------------------------------------------------------------------- |
| `todo add [title]`              | Add a todo. Interactive; any missing option prompts via fzf/gum.    |
| `todo done`                     | Complete todos (fzf multi-select, preview).                         |
| `todo del`                      | Permanently delete todos (fzf multi-select + confirmation).         |
| `todo edit`                     | Open a todo body in `$EDITOR` (fzf single-select).                  |
| `todo show [category]`          | Show active todos, grouped by category and sorted.                  |
| `todo sync`                     | Force a blocking pull -> commit -> push.                            |
| `todo repo [path]`              | Print or switch the active data repo.                               |
| `todo init <path>`              | Initialize/adopt a data repo and set it active.                     |

### `todo add`

Fully non-interactive form (any omitted option triggers its prompt):

```sh
todo add "Renew passport" -c admin -u soon --horizon month --deadline 2026-08-15
todo add "Pay bill" -c admin -u now          # prompts for the horizon
todo add                                     # prompts for everything
```

Add `--edit` to open `$EDITOR` on the new file to write a markdown body.

### `todo show`

```sh
todo show            # all categories
todo show work       # only the "work" category
todo show -u now     # only "now" urgency
todo show --today    # today horizon + today's and overdue deadlines
todo show --done     # the archive
```

Tables adapt to the terminal width (capped at 100 columns) and wrap long titles
instead of truncating them. Overdue deadlines are shown in red with a `⚠`
marker.

## Sync model

The chosen strategy is **instant local commit + best-effort background
network** (never blocking):

1. A mutation (`add`/`done`/`del`/`edit`) writes the file and commits locally
   in a few milliseconds - the command returns immediately.
2. The `pull`/`push` is then delegated to a **detached background process**, so
   the round-trip to the remote (~seconds) never slows you down and works
   offline.
3. A file lock serializes background syncs; the background job **drains** in a
   loop so a burst of quick `add`s all end up pushed.
4. `todo sync` performs a **blocking, guaranteed** sync when you want certainty.

Offline behaviour: the local commit always succeeds; a failed push is recorded
in `<data-repo>/.git/todo-sync.log` and retried on the next mutation or
`todo sync`. Nothing is lost.

Automatic background sync is controlled by `sync.auto` in the repo's
`config.toml` (default `true`). Set it to `false` to only commit locally and
push manually with `todo sync`.

## Configuration

- **Local** (per machine, not versioned): `~/.config/todo/config.toml`

  ```toml
  data_dir = "~/todo-data"
  ```

- **Data repo** (versioned, shared across devices): `<data-repo>/config.toml`

  ```toml
  [categories]
  values = ["work", "home", "perso", "admin"]

  [urgency]
  values = ["now", "soon", "someday"]   # order defines the sort rank
  colors = ["bold red", "yellow", "grey62"]  # parallel to values (rich styles)

  [horizon]
  values = ["today", "week", "month"]   # order defines the sort rank

  [sync]
  auto = true
  ```

Categories, urgencies and horizons are a fixed, finite set defined here. For
`urgency` and `horizon` the **order is meaningful**: the position of a value is
its sort rank (first = most urgent / nearest). `urgency.colors` is optional and
parallel to `urgency.values`.

## Todo file format

```markdown
---
title: "Renew passport"
category: admin
urgency: soon          # now | soon | someday
horizon: month         # today | week | month | null
deadline: 2026-08-15   # optional ISO date
created: 2026-07-05T14:32:01
completed: null        # filled when moved to done/
---

Optional markdown body: notes, links, a checklist...
```

## Development

```sh
pixi run -e dev lint         # ruff check
pixi run -e dev fmt          # ruff format
pixi run -e dev type-check   # mypy
pixi run -e dev test         # pytest + coverage
pixi run -e dev all          # all of the above
```

CI (GitHub Actions) runs lint, test and type-check on every push / PR to
`main` (see `.github/workflows/ci.yml`).

## License

TBD.
