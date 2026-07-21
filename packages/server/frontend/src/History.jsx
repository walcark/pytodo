import { useCallback, useEffect, useState } from 'react'

import { getDone, reopenTodo } from './api.js'

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString()
}

// The archive: completed todos, most recently completed first. Read-only except
// for reopening, which undoes a completion ticked off by mistake; the log stays
// a faithful record otherwise.
export default function History({ onChanged }) {
  const [todos, setTodos] = useState([])
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => getDone().then(setTodos), [])

  useEffect(() => {
    load().catch((e) => setError(String(e)))
  }, [load])

  async function reopen(id) {
    if (busy) return
    setBusy(id)
    setError(null)
    try {
      await reopenTodo(id)
      await load()
      onChanged()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  if (todos.length === 0 && !error) return <p className="empty">No history yet.</p>

  return (
    <>
      {error && <p className="error">{error}</p>}
      <ul className="todo-list">
        {todos.map((todo) => (
          <li key={todo.id} className={`todo done${busy === todo.id ? ' busy' : ''}`}>
            <span className="pill state-done">done</span>
            <span className="todo-title">{todo.title}</span>
            <span className="todo-tags">
              {todo.context && <span className="tag context">{todo.context}</span>}
              {todo.area && <span className="tag area">{todo.area}</span>}
              {todo.completed && <span className="tag date">{formatDate(todo.completed)}</span>}
            </span>
            <button
              className="row-reopen"
              type="button"
              title="Reopen"
              aria-label={`Reopen ${todo.title}`}
              onClick={() => reopen(todo.id)}
              disabled={busy !== null}
            >
              ↩<span className="btn-label"> Reopen</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}
