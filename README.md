# todo

<p align="center">
  <img src="https://github.com/walcark/pytodo/actions/workflows/ci.yml/badge.svg">
  <a href="https://pixi.sh"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue">
</p>

A minimalist CLI to manage todos the **GTD** way, built for fast daily use
(fzf/gum for every interaction) and synchronized across devices through a
dedicated git repository. Capturing a todo takes a second; the rest of the
workflow (clarify, organize, review, engage) has one command each.

The domain model, and the reasoning behind it, lives in
[`docs/model.md`](docs/model.md). This README is the user guide.

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
├── config.toml     # areas / contexts vocabulary, shared across devices
├── todos/          # every non-done todo (whatever its state), one file each
│   └── 20260705-143201-a3f2.md
├── done/           # completed todos (archive)
├── projects/       # one file per multi-step project
└── plans/          # one file per day (see Daily plans)
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

## The GTD workflow

The command surface follows GTD's five steps. That is the whole point of the
tool: separate *capturing* an idea from *deciding* what to do with it.

| Step | Command | What it is for |
| --- | --- | --- |
| **Capture** | `todo add "..."` | Drop the thought into the inbox, zero decisions. |
| **Clarify** | `todo clarify` | Empty the inbox, one item at a time. |
| **Organize** | (the states / contexts / areas / projects below) | Where clarify puts things. |
| **Reflect** | `todo review` | What GTD says is rotting: full inbox, stalled projects... |
| **Engage** | `todo next`, `todo day`, `todo show` | Pick and do the actual work. |

### States

A todo's `state` is where it sits in the workflow:

| State | Meaning |
| --- | --- |
| `inbox` | Captured, not yet clarified. |
| `next` | Actionable, has a context, ready to do. |
| `waiting` | Delegated or blocked (carries `waiting_on`). |
| `someday` | Not committed to (someday/maybe). |
| `done` | Completed (moved to `done/`). |

### The two orthogonal axes: area and context

These answer different questions and never merge back:

- **`area`** - `work` / `home` / `perso` / `admin`. *Which part of my life.* A
  domain of responsibility, used for grouping.
- **`context`** - `@computer` / `@phone` / `@errands` / ... *What I need in
  order to act right now.* Used for **selecting** what to do: "I am at my
  computer with 20 minutes, what can I do?" is `todo next -c @computer`.

"Call the plumber" is `area=home` **and** `context=@phone`. Both are finite,
editable lists (see [Configuration](#configuration)).

### Projects

A project is an *outcome* needing more than one action (`Renew passport`).
`todo clarify` creates one when an item is multi-step, and captures its first
next action. A todo links to its project by id; the project never lists its
actions, so deleting an action can never dangle. GTD's central rule, **every
active project has at least one `next` action**, is exactly what `todo review`
checks for you.

## Commands

| Command                         | What it does                                                        |
| ------------------------------- | ------------------------------------------------------------------- |
| `todo`                          | No subcommand: show today's plan.                                   |
| `todo add [title]`              | Capture a todo into the inbox (no prompts beyond the title).        |
| `todo clarify`                  | Walk the inbox through GTD's decision tree, one item at a time.     |
| `todo next [-c @ctx]`           | List next actions, optionally filtered by context.                 |
| `todo review`                   | Report what is rotting (inbox, stalled projects, ...).             |
| `todo done`                     | Complete todos (fzf multi-select, preview).                         |
| `todo del`                      | Permanently delete todos (fzf multi-select + confirmation).         |
| `todo edit`                     | Open a todo body in `$EDITOR` (fzf single-select).                  |
| `todo day`                      | Build today's plan: carry unfinished items forward, then pick.      |
| `todo doing`                    | Mark planned items of today's plan as in progress.                  |
| `todo history`                  | Show each day's plan, colorized by per-day status.                  |
| `todo show [area]`              | Show active todos, grouped by area and oldest first.                |
| `todo config ...`               | Read and edit the shared areas/contexts vocabulary.                 |
| `todo sync`                     | Force a blocking pull -> commit -> push.                            |
| `todo repo [path]`              | Print or switch the active data repo.                               |
| `todo init <path>`              | Initialize/adopt a data repo and set it active.                     |

### `todo add` (capture)

Capture is deliberately frictionless: it asks nothing beyond the title and lands
the item in the inbox. Deciding comes later, with `todo clarify`.

```sh
todo add "Call the plumber about the leak"
todo add                 # prompts only for the title
todo add "..." --edit    # also open $EDITOR to write a markdown body
```

### `todo clarify`

Walks each inbox item through GTD's tree: actionable or not, multi-step
(a project) or a single action, then the two-minute rule, delegation
(`waiting`), or a `next` action with a context. Stop any time; the rest stays in
the inbox.

### `todo next` / `todo show`

```sh
todo next                # every next action, oldest first
todo next -c @computer   # only what you can do at the computer

todo show                # all active todos, grouped by area
todo show work           # only the "work" area
todo show -s waiting     # filter by state (inbox|next|waiting|someday|done)
todo show --done         # the archive
```

Nothing ranks todos any more: with no urgency field, lists sort by **creation
date, oldest first**. Priority is decided at engage time (`todo day`), not baked
into a field. Tables adapt to the terminal width and wrap long titles instead of
truncating them.

### `todo review`

The weekly review, checked by the tool. It reports, and stays quiet when there
is nothing to fix:

1. the inbox is not empty (with how long the oldest item has sat);
2. **stalled projects** (active, but no `next` action);
3. `next` actions with **no context** (unselectable at engage time);
4. `waiting` items older than `review.waiting_stale_days` (chase them).

## Daily plans

Beside the stock of todos, `todo day` builds a per-day *working set* to track
what you actually do each day, without changing the todo lifecycle.

```sh
todo            # (no subcommand) show today's plan
todo day        # (rollover of yesterday's unfinished items) then pick next actions
todo doing      # move planned items to "in progress"
todo history    # per-day recap, colorized (todo history -t: today only)
```

- **One file per day**: `plans/YYYY-MM-DD.md`, one line per todo, referenced by
  id with a title snapshot. It is a *log*: entries are never removed, so the
  history survives completing or deleting the underlying todo.
- **Only `next` actions are pickable.** A day plan you cannot act on is how a
  list stops being trusted.
- **Per-day status** (`planned` / `doing` / `done`) is a separate axis from the
  global lifecycle (`todos/` vs `done/`). It is encoded as a markdown checkbox
  (`[ ]` / `[/]` / `[x]`), so `todo history` reads like a git diff.
- **`todo done` also ticks the item done in today's plan** when it is there:
  completing a task is completing it for the day too.
- **Rollover**: the first `todo day` of a new day offers to carry the previous
  day's still-open items forward (only those whose todo is still active).

## Sync model

The chosen strategy is **instant local commit + best-effort background
network** (never blocking):

1. A mutation (`add`/`clarify`/`done`/`del`/`edit`/`day`/`config`) writes the
   file and commits locally in a few milliseconds - the command returns
   immediately.
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

> Internally, every mutation goes through a single UI-agnostic **service** layer
> (`service.py`) that commits then schedules the flush, so the CLI (and a future
> server) share one write path.

## Configuration

- **Local** (per machine, not versioned): `~/.config/todo/config.toml`

  ```toml
  data_dir = "~/todo-data"
  ```

- **Data repo** (versioned, shared across devices): `<data-repo>/config.toml`

  ```toml
  [areas]
  values = ["work", "home", "perso", "admin"]

  [contexts]
  values = ["@computer", "@phone", "@errands", "@office", "@home", "@anywhere"]

  [review]
  waiting_stale_days = 7   # a waiting item older than this is flagged

  [sync]
  auto = true
  ```

`areas` and `contexts` are finite, unordered sets. Edit them from the CLI rather
than by hand (the file is regenerated on write):

```sh
todo config                     # print the vocabulary
todo config edit                # open config.toml in $EDITOR
todo config context add @gym
todo config context rm @office  # refused if any todo still uses it
todo config area add health
```

Editing the vocabulary is a mutation like any other: it commits and syncs.
Removing a value still referenced by active todos is refused (it would orphan
them); reassign those todos first.

## Todo file format

```markdown
---
title: "Call the plumber about the leak"
state: next             # inbox | next | waiting | someday | done
context: "@phone"       # what you need to act; null while inbox
area: home              # domain of responsibility; null while inbox
project: null           # project id, or null for a standalone action
waiting_on: null        # who, when state is waiting
created: 2026-07-17T09:12:00
completed: null         # filled when moved to done/
---

Optional markdown body: notes, links, a checklist...
```

A `next` action's title should be a **physical, visible next step** ("Call the
plumber about the leak"), not a topic ("Plumber"). `todo clarify` asks for it.

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
