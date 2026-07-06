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

- **CI** (GitHub Actions): **done** - `.github/workflows/ci.yml` runs `lint`
  (ruff), `test` (pytest + coverage) and `type-check` (mypy) via pixi on every
  push / PR to `main`.
- Still TODO: enforce `ruff format --check` in CI (the `fmt` task exists but is
  local-only for now), and a `pre-commit` hook.
- **CD**: publish to PyPI on tagged releases (build with `hatchling`, publish
  with trusted publishing / OIDC). Then `pipx install todo-cli` works for
  everyone.
- Add a coverage upload (codecov) and a status badge.

## 3. Other useful improvements

- **`todo config`**: edit categories/urgencies/horizons and presentation
  without hand-editing TOML; commits + syncs the change like any mutation.
- **Shell completion**: ship Typer completions for bash/zsh/fish.
- **CLI tests**: cover the Typer commands end-to-end (currently the library
  layer is well covered; the command wiring is not).
- **Conflict helper**: `todo sync` currently reports rebase conflicts and stops.
  Add guidance / a resolver, even though one-file-per-todo makes them rare.
- **Deadline reminders**: a `todo show --today` is manual; consider an optional
  notification hook (desktop/Termux) for due/overdue items.
- **Recurrence & subtasks**: out of scope for v1 (per spec) but frequently
  wanted; design a minimal recurrence field if demand appears.
- **Mobile**: document the Termux + git workflow (the file+git model already
  supports it; nothing to code CLI-side).
- **Web rendering**: the markdown + front matter format is meant to be rendered
  by an existing Django markdown->HTML server; document the integration.
- **Packaging polish**: a proper license, a `py.typed` marker, and a changelog.
