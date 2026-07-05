# Roadmap

Planned and candidate improvements, roughly in priority order.

## 1. Interactive config questionnaire at `init`

Right now `todo init` writes a default `config.toml`. Add an optional guided
setup (fzf/gum) to tailor the data repo config on creation:

- **Categories**: enter your own list instead of the defaults.
- **Table style**: box style / borders for `todo show` (rich box presets).
- **Palette**: urgency colors (now/soon/someday) and overdue color, so `show`
  matches the user's terminal theme.
- **Sync**: choose `auto = true/false` up front.

Implementation notes:
- Extend `RepoConfig` with presentation fields (e.g. `table.box`,
  `colors.urgency`), consumed by `render.py`.
- `--no-interactive` / `--defaults` flag to keep the current one-shot behaviour
  (and for scripting/tests).
- Re-run the questionnaire later with a `todo config` command.

## 2. CI / CD

- **CI** (GitHub Actions): run `ruff check`, `ruff format --check`, and
  `pytest` on every push / PR, on the supported Python versions.
- Add `ruff format` as the formatter and a `pixi run fmt` task; enforce it in
  CI and optionally via a `pre-commit` hook.
- **CD**: publish to PyPI on tagged releases (build with `hatchling`, publish
  with trusted publishing / OIDC). Then `pipx install todo-cli` works for
  everyone.
- Add a coverage report and a status badge.

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
