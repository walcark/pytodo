import { useCallback, useEffect, useState } from 'react'

import {
  addToToday,
  completeTodo,
  deleteTodo,
  getProjects,
  getToday,
  getTodos,
  getViews,
  getVocabulary,
  removeFromToday,
  updateTodo,
} from './api.js'
import Clarify from './Clarify.jsx'
import History from './History.jsx'
import Projects from './Projects.jsx'
import QuickAdd from './QuickAdd.jsx'
import Review from './Review.jsx'
import Routines from './Routines.jsx'
import Sidebar from './Sidebar.jsx'
import Today from './Today.jsx'
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
  const [projects, setProjects] = useState([])
  const [todayIds, setTodayIds] = useState(new Set())
  const [clarifying, setClarifying] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [error, setError] = useState(null)

  const isView = (value) => selection.kind === 'view' && selection.value === value
  const isToday = isView('today')
  const isHistory = isView('history')
  const isReview = isView('review')
  const isProjects = isView('projects')
  const isRoutines = isView('routines')
  // Views with their own component and their own loader.
  const dedicated = isToday || isHistory || isReview || isProjects || isRoutines

  const loadSidebar = useCallback(async () => {
    const [v, vocabulary, plan, projectList] = await Promise.all([
      getViews(),
      getVocabulary(),
      getToday(),
      getProjects(),
    ])
    setViews(v)
    setVocab(vocabulary)
    setTodayIds(new Set(plan.entries.map((e) => e.id)))
    setProjects(projectList)
  }, [])

  const loadTodos = useCallback(async () => {
    // Today, History and Review render dedicated components that load themselves.
    if (
      selection.kind === 'view' &&
      ['today', 'history', 'review', 'projects', 'routines'].includes(selection.value)
    ) {
      setTodos([])
      return
    }
    const [view, filters] = todosQuery(selection)
    setTodos(await getTodos(view, filters))
  }, [selection])

  useEffect(() => {
    loadSidebar().catch((e) => setError(String(e)))
  }, [loadSidebar])

  useEffect(() => {
    loadTodos().catch((e) => setError(String(e)))
  }, [loadTodos])

  // After any mutation, refresh the list, the sidebar counts and today's set.
  const refresh = useCallback(() => {
    Promise.all([loadSidebar(), loadTodos()]).catch((e) => setError(String(e)))
  }, [loadSidebar, loadTodos])

  // Leaving a view stops any clarify session, so the button never lingers.
  // On a phone the drawer must close too, or the pick stays hidden behind it.
  const select = useCallback((next) => {
    setClarifying(false)
    setSidebarOpen(false)
    setSelection(next)
  }, [])

  const onComplete = useCallback(
    async (id) => {
      await completeTodo(id)
      refresh()
    },
    [refresh],
  )

  const onDelete = useCallback(
    async (id) => {
      await deleteTodo(id)
      refresh()
    },
    [refresh],
  )

  const onEdit = useCallback(
    async (id, fields) => {
      await updateTodo(id, fields)
      refresh()
    },
    [refresh],
  )

  const onToggleToday = useCallback(
    async (id) => {
      if (todayIds.has(id)) await removeFromToday(id)
      else await addToToday(id)
      refresh()
    },
    [todayIds, refresh],
  )

  const exitClarify = useCallback(() => {
    setClarifying(false)
    refresh()
  }, [refresh])

  const canClarify = isView('inbox') && todos.length > 0 && !clarifying

  return (
    <div className="app">
      <Sidebar
        views={views}
        vocab={vocab}
        selection={selection}
        onSelect={select}
        open={sidebarOpen}
      />
      {sidebarOpen && (
        <div className="backdrop" onClick={() => setSidebarOpen(false)} />
      )}
      <main className="main">
        <header className="main-header">
          <button
            type="button"
            className="menu-btn"
            aria-label="Open navigation"
            onClick={() => setSidebarOpen(true)}
          >
            ☰
          </button>
          <h1>{selection.label}</h1>
          {!dedicated && <span className="count">{todos.length}</span>}
          {canClarify && (
            <button
              type="button"
              className="clarify-start"
              onClick={() => setClarifying(true)}
            >
              Clarify
            </button>
          )}
        </header>
        {error && <p className="error">{error}</p>}

        {clarifying ? (
          <Clarify
            items={todos}
            vocab={vocab}
            projects={projects}
            onExit={exitClarify}
          />
        ) : isProjects ? (
          <Projects vocab={vocab} onChanged={refresh} />
        ) : isRoutines ? (
          <Routines vocab={vocab} onChanged={refresh} />
        ) : isReview ? (
          <Review />
        ) : isHistory ? (
          <History onChanged={refresh} />
        ) : isToday ? (
          <>
            <QuickAdd onCaptured={refresh} />
            <Today onChanged={refresh} />
          </>
        ) : (
          <>
            <QuickAdd onCaptured={refresh} />
            <TodoList
              todos={todos}
              vocab={vocab}
              projects={projects}
              todayIds={todayIds}
              onComplete={onComplete}
              onDelete={onDelete}
              onEdit={onEdit}
              onToggleToday={onToggleToday}
            />
          </>
        )}
      </main>
    </div>
  )
}
