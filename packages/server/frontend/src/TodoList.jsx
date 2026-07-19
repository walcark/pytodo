import { useEffect, useState } from 'react'

import { hasModifier, isTyping } from './keyboard.js'
import TodoEditor from './TodoEditor.jsx'

// A single row. Focus (keyboard navigation) and edit mode are driven by the
// parent list; the row only owns its in-flight "busy" flag.
function TodoRow({
  todo,
  vocab,
  inToday,
  focused,
  editing,
  onFocus,
  onStartEdit,
  onCancelEdit,
  onComplete,
  onDelete,
  onEdit,
  onToggleToday,
}) {
  const [busy, setBusy] = useState(false)

  const run = (fn) => async () => {
    if (busy) return
    setBusy(true)
    try {
      await fn(todo.id)
    } finally {
      setBusy(false)
    }
  }

  async function save(fields) {
    setBusy(true)
    try {
      await onEdit(todo.id, fields)
      onCancelEdit()
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <li className="todo editing">
        <TodoEditor
          todo={todo}
          vocab={vocab}
          busy={busy}
          onSave={save}
          onCancel={onCancelEdit}
        />
      </li>
    )
  }

  return (
    <li
      className={`todo${busy ? ' busy' : ''}${focused ? ' focused' : ''}`}
      onMouseEnter={onFocus}
    >
      <button
        className="check"
        type="button"
        title="Complete"
        aria-label={`Complete ${todo.title}`}
        onClick={run(onComplete)}
        disabled={busy}
      >
        ✓
      </button>
      <span className={`pill state-${todo.state}`}>{todo.state}</span>
      <span className="todo-title">{todo.title}</span>
      <span className="todo-tags">
        {todo.context && <span className="tag context">{todo.context}</span>}
        {todo.area && <span className="tag area">{todo.area}</span>}
        {todo.waiting_on && <span className="tag waiting">{todo.waiting_on}</span>}
      </span>
      <button
        className={`today-toggle${inToday ? ' in-today' : ''}`}
        type="button"
        title={inToday ? 'Remove from today' : 'Add to today'}
        aria-label={inToday ? `Remove ${todo.title} from today` : `Add ${todo.title} to today`}
        onClick={run(onToggleToday)}
        disabled={busy}
      >
        {inToday ? '★ Today' : '☆ Today'}
      </button>
      <button
        className="row-edit"
        type="button"
        title="Edit"
        aria-label={`Edit ${todo.title}`}
        onClick={onStartEdit}
        disabled={busy}
      >
        ✎
      </button>
      <button
        className="row-del"
        type="button"
        title="Delete"
        aria-label={`Delete ${todo.title}`}
        onClick={run(onDelete)}
        disabled={busy}
      >
        ✕
      </button>
    </li>
  )
}

export default function TodoList({
  todos,
  vocab,
  todayIds,
  onComplete,
  onDelete,
  onEdit,
  onToggleToday,
}) {
  const [focused, setFocused] = useState(0)
  const [editingId, setEditingId] = useState(null)

  // Keep the focused index in range as the list changes underneath it.
  useEffect(() => {
    setFocused((f) => Math.min(Math.max(f, 0), Math.max(todos.length - 1, 0)))
  }, [todos])

  // j/k move focus; x completes, e edits, t toggles today, on the focused row.
  useEffect(() => {
    function onKey(event) {
      if (isTyping() || hasModifier(event) || editingId || todos.length === 0) return
      const current = todos[Math.min(focused, todos.length - 1)]
      if (event.key === 'j') setFocused((f) => Math.min(f + 1, todos.length - 1))
      else if (event.key === 'k') setFocused((f) => Math.max(f - 1, 0))
      else if (event.key === 'x') onComplete(current.id)
      else if (event.key === 'e') setEditingId(current.id)
      else if (event.key === 't') onToggleToday(current.id)
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [todos, focused, editingId, onComplete, onToggleToday])

  if (todos.length === 0) {
    return <p className="empty">Nothing here.</p>
  }

  return (
    <>
      <ul className="todo-list">
        {todos.map((todo, i) => (
          <TodoRow
            key={todo.id}
            todo={todo}
            vocab={vocab}
            inToday={todayIds.has(todo.id)}
            focused={i === focused && editingId === null}
            editing={editingId === todo.id}
            onFocus={() => setFocused(i)}
            onStartEdit={() => setEditingId(todo.id)}
            onCancelEdit={() => setEditingId(null)}
            onComplete={onComplete}
            onDelete={onDelete}
            onEdit={onEdit}
            onToggleToday={onToggleToday}
          />
        ))}
      </ul>
      <p className="kbd-hint">j/k move · x done · e edit · t today · c capture</p>
    </>
  )
}
