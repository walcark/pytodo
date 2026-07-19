import { useEffect, useState } from 'react'

import { getReview } from './api.js'

// One problem section: a heading with a count, then the offending items. Hidden
// entirely when empty, so a clean review shows only the "all clear" message.
function Section({ title, hint, items, render }) {
  if (items.length === 0) return null
  return (
    <section className="review-section">
      <h2>
        {title} <span className="review-count">{items.length}</span>
      </h2>
      {hint && <p className="review-hint">{hint}</p>}
      <ul className="review-list">
        {items.map((item) => (
          <li key={item.id}>{render(item)}</li>
        ))}
      </ul>
    </section>
  )
}

// The weekly review: the four things GTD says rot silently. Read-only, it tells
// you what to go fix in the other views.
export default function Review() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getReview()
      .then(setData)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="empty">Loading…</p>

  const clean =
    data.inbox.length === 0 &&
    data.stalled_projects.length === 0 &&
    data.contextless_next.length === 0 &&
    data.stale_waiting.length === 0

  if (clean) {
    return <p className="empty">Nothing to fix: inbox zero, every project moving. ✨</p>
  }

  return (
    <div className="review">
      <Section
        title="Inbox to clarify"
        hint="Captured but undecided. Clarify them from the Inbox view."
        items={data.inbox}
        render={(t) => <span className="todo-title">{t.title}</span>}
      />
      <Section
        title="Stalled projects"
        hint="Active projects with no next action, so nothing is advancing them."
        items={data.stalled_projects}
        render={(p) => (
          <>
            <span className="todo-title">{p.title}</span>
            {p.area && <span className="tag area">{p.area}</span>}
          </>
        )}
      />
      <Section
        title="Next actions without a context"
        hint="A next action with no context is unselectable. Give it one."
        items={data.contextless_next}
        render={(t) => <span className="todo-title">{t.title}</span>}
      />
      <Section
        title={`Waiting over ${data.waiting_stale_days} days`}
        hint="Delegated or blocked for a while. Time to chase them."
        items={data.stale_waiting}
        render={(t) => (
          <>
            <span className="todo-title">{t.title}</span>
            {t.waiting_on && <span className="tag waiting">{t.waiting_on}</span>}
          </>
        )}
      />
    </div>
  )
}
