import { useState } from 'react'

import { capture } from './api.js'

// Capture is the dominant mobile need: one field, one decision (the title),
// straight to the inbox. Clarifying happens later, in the CLI for now.
export default function QuickAdd({ onCaptured }) {
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const text = title.trim()
    if (!text || busy) return
    setBusy(true)
    try {
      await capture(text)
      setTitle('')
      onCaptured()
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="quick-add" onSubmit={submit}>
      <input
        type="text"
        placeholder="Capture a todo..."
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        aria-label="Capture a todo"
      />
      <button type="submit" disabled={busy || !title.trim()}>
        Add
      </button>
    </form>
  )
}
