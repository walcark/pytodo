import { useEffect, useRef, useState } from 'react'

import { capture } from './api.js'
import { hasModifier, isTyping } from './keyboard.js'

// Capture is the dominant need: one field, one decision (the title), straight
// to the inbox. The `c` shortcut focuses it from anywhere.
export default function QuickAdd({ onCaptured }) {
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    function onKey(event) {
      if (event.key !== 'c' || isTyping() || hasModifier(event)) return
      event.preventDefault()
      inputRef.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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
        ref={inputRef}
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
