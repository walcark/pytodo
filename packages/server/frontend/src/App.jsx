import { useCallback, useEffect, useState } from 'react'

import { getTodos, getViews, getVocabulary } from './api.js'
import QuickAdd from './QuickAdd.jsx'
import Sidebar from './Sidebar.jsx'
import TodoList from './TodoList.jsx'

const DEFAULT_SELECTION = { kind: 'view', value: 'inbox', label: 'Inbox' }

// Turn a sidebar selection into the /api/todos query it stands for.
function todosQuery(selection) {
  if (selection.kind === 'area') return ['all', { area: selection.value }]
  if (selection.kind === 'context') return ['all', { context: selection.value }]
  return [selection.value, {}]
}

export default function App() {
  const [views, setViews] = useState(null)
  const [vocab, setVocab] = useState({ areas: [], contexts: [] })
  const [selection, setSelection] = useState(DEFAULT_SELECTION)
  const [todos, setTodos] = useState([])
  const [error, setError] = useState(null)

  const loadSidebar = useCallback(async () => {
    const [v, vocabulary] = await Promise.all([getViews(), getVocabulary()])
    setViews(v)
    setVocab(vocabulary)
  }, [])

  const loadTodos = useCallback(async () => {
    const [view, filters] = todosQuery(selection)
    setTodos(await getTodos(view, filters))
  }, [selection])

  useEffect(() => {
    loadSidebar().catch((e) => setError(String(e)))
  }, [loadSidebar])

  useEffect(() => {
    loadTodos().catch((e) => setError(String(e)))
  }, [loadTodos])

  // After a capture, refresh both the list and the sidebar counts.
  const refresh = useCallback(() => {
    Promise.all([loadSidebar(), loadTodos()]).catch((e) => setError(String(e)))
  }, [loadSidebar, loadTodos])

  return (
    <div className="app">
      <Sidebar
        views={views}
        vocab={vocab}
        selection={selection}
        onSelect={setSelection}
      />
      <main className="main">
        <header className="main-header">
          <h1>{selection.label}</h1>
          <span className="count">{todos.length}</span>
        </header>
        <QuickAdd onCaptured={refresh} />
        {error && <p className="error">{error}</p>}
        <TodoList todos={todos} />
      </main>
    </div>
  )
}
