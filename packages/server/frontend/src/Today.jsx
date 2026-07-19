import { useCallback, useEffect, useState } from 'react'

import { completeTodo, getToday, getTodos, removeFromToday, setTodayStatus } from './api.js'

// Today's plan: the day's entries with their per-day status (planned / doing /
// done). Reads /api/today for order and status, and the active "today" todos
// for their context/area tags. Complete archives the todo (which also ticks
// the entry done); the status button toggles planned <-> doing.
export default function Today({ onChanged }) {
  const [entries, setEntries] = useState([])
  const [byId, setById] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    const [plan, todos] = await Promise.all([getToday(), getTodos('today')])
    setEntries(plan.entries)
    setById(Object.fromEntries(todos.map((t) => [t.id, t])))
  }, [])

  useEffect(() => {
    load().catch((e) => setError(String(e)))
  }, [load])

  const run = async (fn) => {
    if (busy) return
    setBusy(true)
    try {
      await fn()
      await load()
      onChanged()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (error) return <p className="error">{error}</p>
  if (entries.length === 0) {
    return (
      <p className="empty">
        Nothing planned for today. Add todos with the ☆ Today button.
      </p>
    )
  }

  return (
    <ul className="todo-list">
      {entries.map((entry) => {
        const todo = byId[entry.id]
        const done = entry.status === 'done'
        return (
          <li key={entry.id} className={`todo${done ? ' done' : ''}`}>
            <span className={`pill plan-${entry.status}`}>{entry.status}</span>
            {todo?.routine && <span className="routine-badge" title="Recurring">⟳</span>}
            <span className="todo-title">{entry.title}</span>
            <span className="todo-tags">
              {todo?.context && <span className="tag context">{todo.context}</span>}
              {todo?.area && <span className="tag area">{todo.area}</span>}
            </span>
            {!done && todo && (
              <button
                className={`today-toggle${entry.status === 'doing' ? ' in-today' : ''}`}
                type="button"
                title={entry.status === 'doing' ? 'Back to planned' : 'Mark doing'}
                onClick={() =>
                  run(() =>
                    setTodayStatus(
                      entry.id,
                      entry.status === 'doing' ? 'planned' : 'doing',
                    ),
                  )
                }
                disabled={busy}
              >
                {entry.status === 'doing' ? '❚❚ Doing' : '▶ Doing'}
              </button>
            )}
            {!done && todo && (
              <button
                className="check"
                type="button"
                title="Complete"
                onClick={() => run(() => completeTodo(entry.id))}
                disabled={busy}
              >
                ✓
              </button>
            )}
            <button
              className="row-del"
              type="button"
              title="Remove from today"
              onClick={() => run(() => removeFromToday(entry.id))}
              disabled={busy}
            >
              ✕
            </button>
          </li>
        )
      })}
    </ul>
  )
}
