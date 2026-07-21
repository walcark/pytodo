import { useCallback, useEffect, useState } from 'react'

import {
  captureIntoProject,
  completeProject,
  createProject,
  deleteProject,
  getProjects,
  getProjectTodos,
  reopenProject,
} from './api.js'

// One project row: its counts, a stalled badge, its serving todos (lazy-loaded
// on expand), and a capture bar to drop new todos straight into the project.
function ProjectRow({ project, onCaptured, onError }) {
  const [open, setOpen] = useState(false)
  const [todos, setTodos] = useState(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const done = project.state === 'done'

  const loadTodos = useCallback(async () => {
    setTodos(await getProjectTodos(project.id))
  }, [project.id])

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && todos === null) await loadTodos()
  }

  async function capture(event) {
    event.preventDefault()
    const text = title.trim()
    if (!text || busy) return
    setBusy(true)
    try {
      await captureIntoProject(project.id, text)
      setTitle('')
      await loadTodos()
      onCaptured() // refresh the counts (and the app-wide project list)
    } finally {
      setBusy(false)
    }
  }

  // Actions run through here so a refusal surfaces instead of failing silently.
  const run = (fn) => async () => {
    if (busy) return
    setBusy(true)
    try {
      await fn()
      onCaptured()
    } catch (e) {
      onError(String(e))
    } finally {
      setBusy(false)
    }
  }

  // The outcome closes; its actions stay active, so say so before closing it.
  const confirmComplete = () =>
    project.action_count === 0 ||
    window.confirm(
      `${project.action_count} action(s) still serve "${project.title}". ` +
        'They stay on your lists. Complete the project anyway?',
    )

  // Deleting the target of a reference is the one direction that can dangle,
  // hence the explicit detach rather than a silent rewrite.
  const confirmDelete = () =>
    project.action_count === 0
      ? window.confirm(`Delete "${project.title}"? This cannot be undone.`)
      : window.confirm(
          `${project.action_count} action(s) still reference "${project.title}". ` +
            'Detach them (they are kept, without a project) and delete?',
        )

  return (
    <li className={`project${done ? ' done' : ''}${busy ? ' busy' : ''}`}>
      <button type="button" className="project-head" onClick={toggle}>
        <span className="project-caret">{open ? '▾' : '▸'}</span>
        <span className="project-title">{project.title}</span>
        {project.area && <span className="tag area">{project.area}</span>}
        {done ? (
          <span className="badge done">done</span>
        ) : project.stalled ? (
          <span className="badge stalled">stalled</span>
        ) : (
          <span className="badge">{project.next_count} next</span>
        )}
        <span className="project-count">{project.action_count} action(s)</span>
      </button>
      <div className="project-actions">
        {done ? (
          <button
            type="button"
            className="row-reopen"
            title="Reopen"
            onClick={run(() => reopenProject(project.id))}
            disabled={busy}
          >
            ↩<span className="btn-label"> Reopen</span>
          </button>
        ) : (
          <button
            type="button"
            className="check"
            title="Complete project"
            aria-label={`Complete ${project.title}`}
            onClick={run(async () => {
              if (!confirmComplete()) return
              await completeProject(project.id)
            })}
            disabled={busy}
          >
            ✓
          </button>
        )}
        <button
          type="button"
          className="row-del"
          title="Delete project"
          aria-label={`Delete ${project.title}`}
          onClick={run(async () => {
            if (!confirmDelete()) return
            await deleteProject(project.id, project.action_count > 0)
          })}
          disabled={busy}
        >
          ✕
        </button>
      </div>
      {project.outcome && <p className="project-outcome">{project.outcome}</p>}
      {open && (
        <div className="project-body">
          <ul className="project-todos">
            {todos === null ? (
              <li className="muted">Loading…</li>
            ) : todos.length === 0 ? (
              <li className="muted">No actions yet.</li>
            ) : (
              todos.map((t) => (
                <li key={t.id}>
                  <span className={`pill state-${t.state}`}>{t.state}</span>
                  <span className="todo-title">{t.title}</span>
                  {t.context && <span className="tag context">{t.context}</span>}
                </li>
              ))
            )}
          </ul>
          <form className="project-capture" onSubmit={capture}>
            <input
              type="text"
              placeholder="Capture into this project…"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              aria-label={`Capture into ${project.title}`}
            />
            <button type="submit" disabled={busy || !title.trim()}>
              Capture
            </button>
          </form>
        </div>
      )}
    </li>
  )
}

function CreateProject({ vocab, onCreated }) {
  const [title, setTitle] = useState('')
  const [outcome, setOutcome] = useState('')
  const [area, setArea] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const text = title.trim()
    if (!text || busy) return
    setBusy(true)
    try {
      await createProject({
        title: text,
        outcome: outcome.trim() || null,
        area: area || null,
      })
      setTitle('')
      setOutcome('')
      setArea('')
      onCreated()
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="project-create" onSubmit={submit}>
      <input
        type="text"
        placeholder="New project (the outcome you want)…"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        aria-label="Project title"
      />
      <input
        type="text"
        placeholder="Outcome (optional)"
        value={outcome}
        onChange={(e) => setOutcome(e.target.value)}
        aria-label="Project outcome"
      />
      <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Area">
        <option value="">(no area)</option>
        {vocab.areas.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
      <button type="submit" disabled={busy || !title.trim()}>
        Create
      </button>
    </form>
  )
}

// The projects view: create outcomes, capture actions into them, and see for
// each whether it is moving (has a next action) and the todos that serve it.
export default function Projects({ vocab, onChanged }) {
  const [projects, setProjects] = useState([])
  const [showDone, setShowDone] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setProjects(await getProjects(showDone))
  }, [showDone])

  useEffect(() => {
    load().catch((e) => setError(String(e)))
  }, [load])

  // Reload the summaries locally and let the app refresh the shared list too.
  const onChangedHere = () => {
    setError(null)
    load().catch((e) => setError(String(e)))
    onChanged()
  }

  return (
    <div className="projects">
      <CreateProject vocab={vocab} onCreated={onChangedHere} />
      <label className="show-done">
        <input
          type="checkbox"
          checked={showDone}
          onChange={(e) => setShowDone(e.target.checked)}
        />
        Show completed
      </label>
      {error && <p className="error">{error}</p>}
      {projects.length === 0 ? (
        <p className="empty">No active projects yet.</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <ProjectRow
              key={p.id}
              project={p}
              onCaptured={onChangedHere}
              onError={setError}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
