# Roadmap

Planned and candidate improvements, roughly in priority order.

## 1. Interactive config questionnaire at `init`

Right now `todo init` writes a default `config.toml`. Add an optional guided
setup (fzf/gum) to tailor the data repo config on creation:

- **Categories**: enter your own list instead of the defaults.
- **Urgency / horizon**: reorder the levels and (for urgency) pick colors.
  These are already config fields (`urgency.values` / `urgency.colors`,
  `horizon.values`); the questionnaire would just populate them interactively.
- **Table style**: box style / borders for `todo show` (rich box presets).
- **Overdue color**: currently a hardcoded `OVERDUE_STYLE`; expose it in config.
- **Sync**: choose `auto = true/false` up front.

Implementation notes:
- `RepoConfig.urgency` / `horizon` are already `Scale` objects (ordered values
  + colors) consumed by `render.py`. Remaining presentation fields to add:
  `table.box` and `colors.overdue`.
- `--no-interactive` / `--defaults` flag to keep the current one-shot behaviour
  (and for scripting/tests).
- Re-run the questionnaire later with a `todo config` command.

## 2. CI / CD

- **CI** (GitHub Actions): **done** - `.github/workflows/ci.yml` runs
  `fmt-check` (ruff format), `lint` (ruff check), `test` (pytest + coverage)
  and `type-check` (mypy) via pixi on every push / PR to `main`.
- Still TODO: a `pre-commit` hook mirroring the CI checks locally.
- **CD**: publish to PyPI on tagged releases (build with `hatchling`, publish
  with trusted publishing / OIDC). Then `pipx install todo-cli` works for
  everyone.
- Add a coverage upload (codecov) and a status badge.

## 3. Daily plans (`todo day`)

The stock of todos (`todo show`) answers *what is there to do*, not *what am I
working on today*. Daily plans add a lightweight, per-day working set with
progress tracking, layered **on top of** the todo lifecycle without altering it.

### Model: the daily file is a *log of references*, not a store

One file per day, `plans/2026-07-15.md` (ISO date, so files sort
chronologically — consistent with the `20260705-...` todo-id convention). Each
line references one todo *by id* and carries a **per-day status**, encoded as a
markdown checkbox so that `todo history` renders as a git-style diff for free:

```markdown
---
date: 2026-07-15
---
- [ ] 20260705-143201-a3f2  Renew passport   # planned
- [/] 20260706-091200-b1c3  Write report     # in progress
- [x] 20260701-120000-77de  Pay bill         # done today
```

Rules that fall out of this:

- **Single source of truth.** The daily file stores only `id + a title
  snapshot`, never a copy of the todo content. `todos/<id>.md` stays the only
  source of truth. This is what dissolves the "an item lives in two files"
  problem — there is no duplicated content to keep in sync.
- **Nothing is ever removed from a daily file.** When `todo done` / `todo del`
  archive or delete the underlying todo, its reference is left dangling *on
  purpose* — that is the history. The stored title snapshot keeps the log
  **self-contained**, so `todo history` still renders correctly even after the
  todo has left `todos/`.
- `todo add` / `todo done` / `todo del` / `todo edit` never touch daily files.
  Daily plans are a separate, additive layer.

### Two distinct "done"s — keep them apart

State this explicitly, or the implementation will conflate them:

- **Global lifecycle** — `todo done` moves a todo `todos/ → done/`. The task is
  finished, period.
- **Daily status** — `[ ] / [/] / [x]` inside a daily file means *did I work on
  it today*. A multi-day task can be `[x]` (done today) on Monday and still be
  globally active.

They are independent axes.

### Commands

- `todo day` — fzf-pick from active todos; selected ones are appended (status
  `planned`) to today's file, creating it if needed. Re-running the same day
  appends to the existing file. Named `day` (not `today`) to avoid colliding
  with the existing `todo show --today` horizon filter.
- `todo doing` — mark a planned item as in progress. *Candidate — see "start
  minimal" below.*
- `todo history` — per-day summary with colorized statuses (green done / orange
  doing / red planned), git-diff style.

All progress mutations still go through the `todo` cli — the daily file is never
hand-edited in normal use.

### Sync: a single shared file per day, kept conflict-safe

Rejected: one file per machine — illogical, and it fragments a single day across
devices.

Adopted: **one shared `plans/2026-07-15.md`**, made safe by two things working
together:

1. **Line-oriented structure.** One line per todo, keyed by id. Two devices
   adding *different* todos to the same day touch *different lines* → git merges
   them automatically. This is what lets a shared aggregate file coexist with
   the "one file per todo" pillar.
2. **The existing sync model already fits.** Mutations already do an instant
   local commit + a background pull→push, so a `todo day` picks up remote state
   and pushes its own with no perceptible latency. Being a deliberate,
   once-a-day action, `todo day` can even afford a short **blocking**
   pull→commit→push for stronger freshness. Other/read actions stay
   non-blocking — we do **not** add blocking pulls everywhere, as that would
   break the "never blocking" guarantee.

Residual conflict — and it is the *only* one: the **same todo's status** edited
differently on **two offline devices the same day** (e.g. `[/]` on the laptop,
`[x]` on the phone, both before either syncs). Rare, and resolvable with a fixed
precedence `done > doing > planned` (highest wins on merge). Document it; do not
over-engineer it.

### Open questions

- **Rollover.** On the first `todo day` of a new day, offer to carry forward the
  previous day's unfinished (`planned` / `doing`) items. Decide the source: only
  yesterday, or the last non-empty day.
- **Start minimal (YAGNI).** Ship two states (`planned` / `done`) first; add
  `doing` (and the `todo doing` command) only once the need is confirmed.

### MVP

`todo day` (pick → write `id + title` refs, status `planned`) + `todo history`
(colorized render). Defer: `doing`, rollover, and subtasks (§5).

## 4. Mobile capture

The dominant mobile need is **capture** — dropping a task the moment it comes to
mind — not full management. Completing / reorganizing can stay on desktop / CLI.
So optimize mobile for capture first (GTD: capture ≠ process). `todo add` over
Termux is too heavy for this, and a native Android app is disproportionate (a
PWA replaces it — see 4b).

Two options, ordered by infrastructure cost.

### 4a. Inbox + synced folder (no server) — near-term

An `inbox` file in the data repo. On mobile, a home-screen text widget (via
Nextcloud Notes, Syncthing, or similar) *appends a raw line*. On desktop a new
`todo inbox` command reads those lines and turns each into a real todo
(category / urgency picked via fzf, one at a time).

- **Mobile friction**: minimal — one line, one tap.
- **Cost**: near zero; no server, no auth, no frontend.
- **Trade-off**: two-step capture (raw line → desktop triage). A raw inbox line
  is *not* a todo until processed — which neatly sidesteps the "editing raw
  markdown on mobile bypasses the CLI's invariants" trap, since inbox lines were
  never todos to begin with.
- Nextcloud (or Syncthing) is used here purely as a **file-sync transport**.

### 4b. Web app / PWA (Django, git backend) — later, needs a server

The "web page with a button per action" idea, and it is architecturally clean:
pytodo's library layer (`storage` / `gitrepo` / `config` / `models`) is separate
from `cli.py`, so the planned Django markdown->HTML renderer (§5, *Web
rendering*) can **import and call the same core directly** — CLI and web share
one code path, zero duplication.

- The renderer gains write endpoints (`add` / `done` / `del`) that call
  `storage.save_todo` + `gitrepo.sync`, exactly like the CLI. The server becomes
  just another git writer → pull-before-write / push-after keeps the
  conflict-free property.
- Ship it as a **PWA** ("add to home screen"): behaves like an app, one tap, no
  Kotlin, no app store, no native Android work.
- **Requires** an always-on server reachable from mobile (home server +
  Tailscale/VPN, or a small VPS) and **authentication** — never expose write
  endpoints unauthenticated. Blocked on the home-server project maturing.

**Not** adopting Nextcloud Tasks / CalDAV as the task *backend*: it would give a
free native mobile app (à la Planify) but only by abandoning markdown+git as the
source of truth (or maintaining a git↔CalDAV two-way bridge). Nextcloud stays a
file-sync transport (4a), not the store.

## 5. Other useful improvements

- **`todo config`**: edit categories/urgencies/horizons and presentation
  without hand-editing TOML; commits + syncs the change like any mutation.
- **Shell completion**: ship Typer completions for bash/zsh/fish.
- **CLI tests**: cover the Typer commands end-to-end (currently the library
  layer is well covered; the command wiring is not).
- **Conflict helper**: `todo sync` currently reports rebase conflicts and stops.
  Add guidance / a resolver, even though one-file-per-todo makes them rare.
- **Deadline reminders**: a `todo show --today` is manual; consider an optional
  notification hook (desktop/Termux) for due/overdue items.
- **Subtasks**: for a lightweight breakdown, the todo **body already supports a
  markdown checklist** (`- [ ]`) — zero code, use it first. Promote to
  *first-class* subtasks (a `parent: <id>` front-matter field, one file per
  subtask) only when a subtask needs its **own** urgency/deadline/daily
  planning. That is also the only case where "show the parent context"
  rendering (`Subtask (Parent)`, which gets unreadable for long titles) matters
  — and it needs rules: does completing all children auto-complete the parent?
  How does `todo day` treat a parent vs a leaf? Kept out of v1.
- **Recurrence**: out of scope for v1 (per spec) but frequently wanted; design a
  minimal recurrence field if demand appears.
- **Web rendering**: the markdown + front matter format is meant to be rendered
  by an existing Django markdown->HTML server; document the integration.
- **Packaging polish**: a proper license, a `py.typed` marker, and a changelog.
