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

**Status: implemented.** `todo day` / `todo doing` / `todo history` ship with
three per-day states (`planned` / `doing` / `done`) and rollover. Model in
`plan.py`, storage in `storage.py`, rendering in `render.py`. The notes below
are the design rationale (kept for reference); remaining ideas are in
*Follow-ups* at the end.

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
- **One deliberate coupling** (decided during implementation): `todo done` also
  ticks the item `[x]` in *today's* plan when it is present — completing a task
  is completing it for the day. `add` / `del` / `edit` still never touch daily
  files. A `del`-ed todo's entry stays as-is (dangling, by the "never remove"
  rule above).

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
  appends. Named `day` (not `today`) to keep the plan verb distinct from a
  stock view.
- `todo doing` — mark planned items of today's plan as in progress (fzf
  multi-select over the planned entries).
- `todo history` — per-day summary with colorized statuses (green done / yellow
  doing / grey planned), git-diff style. `-t` / `--today` shows only today.
- **`todo` (no subcommand)** — the daily dashboard: prints today's plan (or a
  hint to run `todo day`). This is the intended most-frequent command.

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

### Resolved decisions

- **Rollover.** The first `todo day` of a day offers to carry forward the **last
  non-empty day's** still-open (`planned` / `doing`) items, and only those whose
  todo is still active (globally done/deleted ones are dropped). Carried items
  come back as `planned`.
- **States.** Shipped with all three (`planned` / `doing` / `done`), not the
  two-state MVP — `doing` was a core part of the original need.

### Follow-ups (not done)

- **Merge precedence on conflict** (`done > doing > planned`): documented above,
  not yet enforced by code (relies on git's line merge for now).
- **Subtasks** (§5): entries reference todos by id, so first-class subtasks slot
  in as ordinary entries later without changing the file format.

## 4. Frontends beyond the CLI (mobile & desktop)

All of these are **frontends on the shared core**: they reuse neverland's library
layer (`storage` / `gitrepo` / `config` / `models` / `plan`) and swap only the
edges (`ui.py` fzf/gum, `render.py` rich). None of them reimplement the todo
logic or shell out to the CLI. 4a is a no-server fallback for mobile capture,
4b (`neverland-server`) is the real mobile answer, 4c is the desktop GUI.

The dominant mobile need is **capture** — dropping a task the moment it comes to
mind — not full management. Completing / reorganizing can stay on desktop / CLI.
So optimize mobile for capture first (GTD: capture ≠ process). `todo add` over
Termux is too heavy for this, and a native Android app is disproportionate (a
PWA replaces it — see 4b).

Two mobile options, ordered by infrastructure cost.

### 4a. Inbox + synced folder (no server) — optional fallback

Only worth it if the `neverland-server` (4b) is not up yet: it needs no server at
all. Once 4b exists, its "quick add" field covers capture and this becomes
redundant.


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

### 4b. `neverland-server`: self-hosted web app / PWA — the real mobile answer

Goal: usable from the **phone's browser, zero install** (optionally "add to home
screen" as a PWA — app-like, no app store). A web page that *mutates* todos
needs a backend, so this is a small self-hosted server, `neverland-server`, on one
always-on machine (home server / Raspberry Pi / small VPS). It **subsumes 4a**:
with a real server, mobile capture is just a "quick add" field.

Architecture (one process):

```
   phone (browser / PWA)
        │  HTTP(S)
        ▼
  neverland-server ── import neverland (storage / plan / models / gitrepo / config)
   - serves the PWA (HTML/JS)
   - read/write API: GET /today /stock ; POST /add /done /doing /day
   - sync orchestration (shared auto_sync)
   - holds a git working copy of the data repo
        │  git pull / push
        ▼
  personal remote (GitHub / GitLab / Nextcloud-hosted git)
        ▲
        │  todo sync
  desktop CLI
```

- **Frontend on the shared core**: the server `import`s neverland and calls the
  same functions as the CLI (`storage.*`, `create_todo`, `gitrepo.sync`), never
  shells out. It replaces the edges (`ui.py` → tap targets, `render.py` → HTML).
- **"Connect a personal repo" = a git remote + credentials.** The model is
  already git, so the server config is `{ remote_url, auth, local_path }`.
  GitHub/GitLab are natural remotes (SSH key / token); Nextcloud only if it
  *hosts a git repo* (its plain file-sync mode drops git as the transport —
  avoid).
- **Just another git writer**, coordinated with the desktop CLI through the
  remote: pull-before-write / push-after under the same `sync_lock`, so the
  conflict-free property (one file per todo + line-oriented plan) holds.
- **Prerequisite refactor** (shared with 4c): extract the mutation orchestration
  (`auto_sync` = local commit + background flush, today in `cli.py`) into a
  UI-agnostic module used by CLI, server and GUI.

Operational must-haves:

- **Reachability**: **Tailscale** (or WireGuard) is the sweet spot — the phone
  joins the tailnet and reaches `http://neverland.<tailnet>` with **no public
  exposure, no open ports**. Alternatives if a public URL is wanted: Caddy +
  Let's Encrypt + auth, or a Cloudflare Tunnel.
- **Auth is mandatory**, even behind the VPN: a single-user token / basic auth.
  Never expose write endpoints unauthenticated.
- **Pull cadence**: pull-before-write plus a periodic background pull (every N
  seconds) to reflect CLI/other-device changes — not a pull on every read
  (latency).
- **Stack**: **FastAPI** (lean, serves API + static PWA) by default; Django only
  if reusing the existing markdown->HTML server (§5, *Web rendering*).

**Not** adopting Nextcloud Tasks / CalDAV as the task *backend*: it would give a
free native mobile app (à la Planify) but only by abandoning markdown+git as the
source of truth (or maintaining a git↔CalDAV two-way bridge). Nextcloud stays a
git host or file-sync transport, not the store.

### 4c. Desktop GUI (pure frontend on the shared core) — later

A more visual desktop app, built as a **separate `neverland-gui` package** that
depends on `neverland` and reuses its library directly (never shelling out to the
CLI, whose output is for humans). The GUI swaps only the edges for widgets; the
core is already UI-agnostic.

- **Prerequisite refactor**: the same `auto_sync` extraction as 4b (a
  UI-agnostic orchestration module shared by CLI, server and GUI). The GUI is
  then just another git writer through `sync` + `sync_lock`.
- **Live refresh**: watch the repo (e.g. `watchdog`) to re-render when another
  device syncs.
- **Toolkit options (undecided, choose later)**:
  - **GTK4 / libadwaita** (PyGObject): native on GNOME/Fedora, Planify-like.
  - **PySide6 (Qt)**: more portable, quicker to start.
  - **Webview** (pywebview) reusing the future web frontend (4b): one UI, two
    shells (desktop + mobile PWA), at the cost of pulling in a web stack.

## 5. Other useful improvements

- **`todo config`**: edit categories/urgencies/horizons and presentation
  without hand-editing TOML; commits + syncs the change like any mutation.
- **Shell completion**: ship Typer completions for bash/zsh/fish.
- **CLI tests**: cover the Typer commands end-to-end (currently the library
  layer is well covered; the command wiring is not).
- **Conflict helper**: `todo sync` currently reports rebase conflicts and stops.
  Add guidance / a resolver, even though one-file-per-todo makes them rare.
- **Deadlines (removed for now)**: the hard `deadline` date field was dropped
  (rarely a real date in practice; urgency + horizon + the daily plan cover the
  need). Reintroduce later *with* a design for how a hard date coexists with
  urgency/horizon and the daily plan (sort weight, an overdue signal, and a
  possible reminder hook) — not as a bare field bolted back on.
- **Subtasks**: for a lightweight breakdown, the todo **body already supports a
  markdown checklist** (`- [ ]`) — zero code, use it first. Promote to
  *first-class* subtasks (a `parent: <id>` front-matter field, one file per
  subtask) only when a subtask needs its **own** urgency/horizon/daily
  planning. That is also the only case where "show the parent context"
  rendering (`Subtask (Parent)`, which gets unreadable for long titles) matters
  — and it needs rules: does completing all children auto-complete the parent?
  How does `todo day` treat a parent vs a leaf? Kept out of v1.
- **Recurrence**: out of scope for v1 (per spec) but frequently wanted; design a
  minimal recurrence field if demand appears.
- **Web rendering**: the markdown + front matter format is meant to be rendered
  by an existing Django markdown->HTML server; document the integration.
- **Packaging polish**: a proper license, a `py.typed` marker, and a changelog.
