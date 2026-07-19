import { useCallback, useEffect, useState } from 'react'

import {
  captureIntoProject,
  createProject,
  getProjects,
  getProjectTodos,
} from './api.js'

// One project row: its counts, a stalled badge, its serving todos (lazy-loaded
// on expand), and a capture bar to drop new todos straight into the project.
function ProjectRow({ project, onCaptured }) {
  const [open, setOpen] = useState(false)
  const [todos, setTodos] = useState(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

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

  return (
    <li className="project">
      <button type="button" className="project-head" onClick={toggle}>
        <span className="project-caret">{open ? '▾' : '▸'}</span>
        <span className="project-title">{project.title}</span>
        {project.area && <span className="tag area">{project.area}</span>}
        {project.stalled ? (
          <span className="badge stalled">stalled</span>
        ) : (
          <span className="badge">{project.next_count} next</span>
        )}
        <span className="project-count">{project.action_count} action(s)</span>
      </button>
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
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setProjects(await getProjects())
  }, [])

  useEffect(() => {
    load().catch((e) => setError(String(e)))
  }, [load])

  // Reload the summaries locally and let the app refresh the shared list too.
  const onChangedHere = () => {
    load().catch((e) => setError(String(e)))
    onChanged()
  }

  return (
    <div className="projects">
      <CreateProject vocab={vocab} onCreated={onChangedHere} />
      {error && <p className="error">{error}</p>}
      {projects.length === 0 ? (
        <p className="empty">No active projects yet.</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <ProjectRow key={p.id} project={p} onCaptured={onChangedHere} />
          ))}
        </ul>
      )}
    </div>
  )
}
