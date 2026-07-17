# The GTD model

Status: **spec, not implemented**. This is phase 1 of the restructuring plan
(see the bottom of this file). No code follows this document yet.

This file is the source of truth for the domain model. `ROADMAP.md` tracks
features; this tracks *meaning*.

## Why change the model at all

The current model has three structural problems with respect to GTD:

1. **There is no context axis.** `category` (`work` / `home` / `perso` /
   `admin`) is an *area of responsibility*: it answers "which part of my life".
   A GTD context (`@computer`, `@phone`, `@errands`) answers "what do I need in
   order to act right now". These are orthogonal: "call the plumber" is
   `area=home` **and** `@phone`. The fact that `home` currently appears as a
   category is the symptom. The question that matters when acting is "I am at my
   computer with 20 minutes free, what can I do?", and the current model cannot
   answer it.

2. **`todo add` fuses capture and clarify.** It prompts for category, urgency
   and horizon at the exact moment you have merely had an idea. GTD separates
   the two because capture must be frictionless (~1 second, zero decisions) or
   you stop capturing. Clarifying is a separate, deliberate pass.

3. **`urgency: someday` conflates a state with a priority.** In GTD,
   someday/maybe is a *list*, an engagement level, not a priority rank. It
   belongs in `state`.

And two redundancies:

- **`horizon` is not GTD and duplicates the daily plan.** GTD is firm that a
  non-date-specific item is a next action chosen by context, not something
  pre-assigned to a week. `todo day` already performs that selection, and does
  it better. Two mechanisms for one job.
- **`urgency` duplicates the daily plan too** (see the non-goals below). It goes
  as well, and takes more code with it than anything else here.

## The five steps map onto the command surface

| GTD step | Commands |
| --- | --- |
| **Capture** | `todo add "..."` (straight to inbox, no prompts) |
| **Clarify** | `todo clarify` (empties the inbox, one decision at a time) |
| **Organize** | the states, contexts and projects below |
| **Reflect** | `todo review` |
| **Engage** | `todo day`, `todo doing`, `todo next -c @computer`, `todo show` |

`todo day` and the daily plan are unchanged: they *are* the engage step, and
only now get their proper name.

## States

```
inbox    captured, not yet clarified
next     actionable, has a context, ready to do
waiting  delegated or blocked (carries waiting_on)
someday  not committed to
done     completed
```

`state` is a **front matter field**, not a directory, for `inbox` / `next` /
`waiting` / `someday`. Only the move to `done/` stays a file move.

Rationale: clarifying an item would otherwise rewrite its path and produce a
rename in git on every state change. The `todos/` vs `done/` split is worth a
move because it bounds what `list_active` reads and keeps the archive out of the
working set. The id, and therefore the file stem, never changes (unchanged rule).

`state` is also what carries **colour** in the rendered lists, now that
`urgency` is gone. That is more GTD-truthful anyway: `waiting` stands out
because it is blocked on someone else, not because it is "urgent".

## The two orthogonal axes

Keep them separate, and never merge them back:

- **`area`** (was `category`): `work` / `home` / `perso` / `admin`. A domain of
  responsibility. Used for grouping and reporting.
- **`context`**: `@computer` / `@phone` / `@errands` / `@office` / `@home` /
  `@anywhere`. A precondition for acting. Used for **selecting what to do**.

Both are finite sets defined in the repo config, both editable at runtime (see
"Editing the vocabulary"). Neither is ordered.

A context is only worth having if you are regularly *in* it. A context you never
filter on is noise, and it makes every clarify prompt longer.

## Todo

```markdown
---
title: "Call the plumber about the leak"
state: next             # inbox | next | waiting | someday | done
context: "@phone"       # null while state is inbox
area: home              # null while state is inbox
project: null           # project id, or null for a standalone action
waiting_on: null        # who, when state is waiting
created: 2026-07-17T09:12:00
completed: null
---

Optional markdown body.
```

A `next` action's title must be a **physical, visible next step** ("Call the
plumber about the leak"), not a topic ("Plumber"). The tool cannot enforce this,
but `todo clarify` should ask for it explicitly.

### Ordering

With `urgency` and `horizon` both gone, nothing ranks todos any more. Lists sort
by **creation date, oldest first**.

Age is the only honest signal left, and it has the right property: something old
taps you on the shoulder. Any other order would be reintroducing a priority
field through the back door, which is exactly what GTD says not to do (priority
is decided at engage time, and `todo day` is where that happens).

## Project

A project is an *outcome* requiring more than one action. This is also the
answer to the subtasks question that was deferred in `ROADMAP.md` §5: a parent
todo with children is just a project with next actions, and it needs no new
mechanism.

```markdown
---
title: "Renew passport"
outcome: "Valid passport in hand"
area: admin
state: active           # active | someday | done
created: 2026-07-17T09:12:00
completed: null
---

Notes, links, reference material.
```

Todos reference a project by id (`project: 20260717-091200-a3f2`). The project
never lists its actions: the reference points one way only, so deleting an
action cannot leave a dangling list. Same reasoning as the daily plan being a
log of references.

## The invariant the tool can enforce

> **Every active project has at least one `next` action.**

This is GTD's central operational rule and the one humans always break. A tool
can check it for free, which is exactly the kind of thing worth building:

```
active project + zero todos with state=next and project=<id>  ->  STALLED
```

`todo review` surfaces:

1. inbox is not empty (count, plus how long the oldest item has sat)
2. **stalled projects** (the invariant above)
3. `next` actions with no context (they are unselectable at engage time)
4. `waiting` items older than `review.waiting_stale_days` (chase them)

## The clarify decision tree

`todo clarify` walks the inbox, one item at a time, following GTD literally:

```
Is it actionable?
├── No  ──> trash (todo del) | someday
└── Yes ──> Is it multi-step?
            ├── Yes ──> create a Project, then capture its first next action
            └── No  ──> Under 2 minutes?   ──> do it now, mark done immediately
                        Someone else's?    ──> waiting  (+ waiting_on)
                        Otherwise          ──> next     (+ context)
```

The two-minute rule is worth implementing as a real prompt: it is the highest
leverage part of GTD and it is trivial here (`done` immediately).

## Repo config (vocabulary)

```toml
[areas]
values = ["work", "home", "perso", "admin"]

[contexts]
values = ["@computer", "@phone", "@errands", "@office", "@home", "@anywhere"]

[review]
waiting_stale_days = 7

[sync]
auto = true
```

`horizon` and `urgency` are both gone, and with them the `[urgency]` colours.

**This kills `Scale` and `make_sort_key`.** `Scale` (a frozen dataclass carrying
an *ordered* value list plus per-value colours) existed only to serve `urgency`
and `horizon`. `areas` and `contexts` are flat unordered lists. The vocabulary
collapses to two lists, and `models.make_sort_key` has no caller left once
ordering is by creation date. Delete both rather than finding them a new job.

## Editing the vocabulary

Contexts and areas must be editable at runtime, from the CLI now and from the
web UI later.

```
todo config                      # open $EDITOR on config.toml
todo config show
todo config context add @gym
todo config context rm @office
todo config area add health
```

Three consequences that are easy to miss:

**Editing the config is a mutation.** `config.toml` lives in the data repo: it
is versioned and shared across devices, not a local preference file. So
`todo config` goes through the same service path as any write (commit locally,
schedule the background flush). It is not a special case.

**Removing a value that todos still reference needs a rule.** Deleting
`@office` while twelve todos carry `context: "@office"` must not silently orphan
them. Refuse by default and report the count; `--force` orphans them, and
`todo review` already reports contextless `next` actions, so they resurface
rather than vanish.

**pytodo owns `config.toml`, so regenerating it is fine.** `tomllib` is
read-only (there is no `tomllib.dumps`), so the existing `to_toml()` rebuilds
the file from the parsed values rather than editing it in place. That loses any
hand-written comment. Accepted deliberately: the file is generated by
`todo init` and maintained through `todo config`, and nobody writes comments in
it. The consequence is that `core` needs **no round-trip TOML dependency**
(`tomlkit` and friends) and stays on `pyyaml` alone, with one write path serving
both the CLI and the web UI.

## Storage layout

```
data/
├── config.toml
├── todos/          # every non-done todo, whatever its state
├── done/           # archive
├── projects/       # one file per project
└── plans/          # one file per day (unchanged)
```

## Migration from the current format

| Current | Becomes |
| --- | --- |
| `category: X` | `area: X` |
| `urgency: someday` | `state: someday` |
| `urgency: now\|soon` | `state: next` |
| `horizon: *` | dropped |
| (none) | `context: null`, flagged by `todo review` |

Nothing lands in `inbox`: existing todos were already clarified under the old
model, so calling them `next` is truthful. They are merely contextless, which
`todo review` will report as a backlog to work through, rather than dumping the
whole list back into the inbox.

## Deliberate non-goals

- **`urgency`, or any priority field.** GTD holds that priority is situational,
  decided at engage time against your actual horizons, and `todo day` is exactly
  that decision. A residual two-level flag would be a vestige: it would get set
  once at clarify time and never revisited, which is worse than no signal at
  all. Ordering by age is honest; ordering by a stale flag is not.
- **`energy` and `time estimate` fields.** They are genuine GTD engage criteria,
  but they are the classic over-modelling trap for a solo tool: fields nobody
  fills in, that then make every prompt longer. Revisit only if `todo day`
  selection actually proves hard in practice.
- **Deadlines / a calendar.** Removing `deadline` was already GTD-correct: GTD
  puts date-specific commitments on the calendar and nowhere else. If a hard
  date appears, it belongs in a real calendar, not here.
- **Reference material.** GTD's "not actionable" branch classically has a third
  outcome besides trash and someday: *reference*, information you will never do
  and only ever look up. pytodo does not store it and `todo clarify` does not
  offer the branch, so "not actionable" is just trash or someday. A todo tool
  that grows into a notes tool ends up mediocre at both.

## The restructuring plan

Order matters more than content here. The package split comes **last**: the real
debt today is that `auto_sync` and the command bodies live in `cli.py`.
Splitting first would only relocate that behind a distribution boundary, where
it is harder to fix. The boundary should be discovered by the refactor, not
imposed on it.

1. **Freeze the model** — this document.
2. **Model + migration**, inside the current single package, with tests. The
   risky phase; do it while the code is still one piece.
3. **Extract the service layer** out of `cli.py` into `core/service.py`.
4. **Rename modules** — mechanical moves, one commit, no behaviour change.
5. **Split the packages** — near-trivial once 1 to 4 are done.
6. **The server.**

`gitrepo.py` is ported, not rewritten. Its 605 lines encode create-or-validate,
nested repos, the `flock` drain loop, the `_commit_scoped` retry and the offline
path. Those live in the edge cases, not in the design, and a rewrite loses them
silently.

### Target module names

Every rename below has a reason; the current names are not merely unfashionable.

| Current | Becomes | Why |
| --- | --- | --- |
| `gitrepo.py` | `vcs.py` | "repo" collides three ways: the git repository, the user's *data repo*, and the Repository pattern that `storage.py` implements. The worst name in the project. |
| `models.py` | `todo.py` | "models" is a Django-ism meaning "ORM tables". This is one dataclass plus parsing, and `plan.py` is equally a model yet sits outside it: the name is inconsistent with its own neighbour. |
| `storage.py` | `store.py` | Same meaning, but the `store/` (files) vs `vcs/` (history and sync) pair finally makes the boundary readable from the names alone. |
| `config.py` | `vocabulary.py` + `settings.py` | It holds two unrelated things. "Where is my data" is a machine-local setting; "which values are legal" (areas, contexts) is *domain*, not config. Splitting makes the layering honest. |
| `ui.py` | `prompt.py` | "ui" suggests the whole interface; it is only the fzf/gum prompts. `render.py` is just as much "ui". |
| `render.py` | `view.py` | Symmetry with `prompt.py`: input and output. |
| (new) | `core/service.py` | The use cases composing `store` + `vcs` (`capture`, `clarify`, `complete`, `plan_day`, `set_vocabulary`). Where `auto_sync` belongs. Not `actions.py`: "action" is taken by the domain, and reusing it would repeat exactly the sin of `gitrepo.py`. |
| `models.make_sort_key` | (deleted) | No caller once ordering is by creation date. |
| `config.Scale` | (deleted) | Existed only for `urgency` and `horizon`. |

`vcs` stays a **single module**, not a `vcs/` package split into `git.py` /
`layout.py` / `sync.py` as an earlier draft of this plan proposed. Its public
API is a flat set of verbs (`sync`, `setup_repo`, `run_git`), which reads well
as `vcs.sync(...)` and badly as `sync.sync(...)`. Worse, a `vcs/sync.py`
submodule would make `vcs.sync` mean both a module and a function, which is the
same class of collision this rename exists to remove. 605 lines with clear
section dividers is navigable; split it when there is a reason beyond the line
count.

### Target packages

Three distributions in one monorepo, sharing the `pytodo` namespace (PEP 420:
**no** `pytodo/__init__.py` in any of them).

```
pytodo-core     pytodo/core/    todo, project, plan, vocabulary, settings,
                                store, vcs, service
                                deps: pyyaml
pytodo-cli      pytodo/cli/     main, prompt, view, commands/
                                deps: pytodo-core, typer, rich
pytodo-server   pytodo/server/  app, api, web/, poller
                                deps: pytodo-core, fastapi, uvicorn
```

`core` spans L1 + L2 + the service layer. That last one is what keeps the CLI
and the server thin; without it both would reimplement "write, commit, schedule
the flush" independently.
