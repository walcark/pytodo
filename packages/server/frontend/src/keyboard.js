// Shared guards for global keyboard shortcuts. A shortcut must never fire while
// the user is typing in a field or holding a modifier (those belong to the
// browser / the input), so every handler checks these first.

export function isTyping() {
  const el = document.activeElement
  return (
    el != null &&
    (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA')
  )
}

export function hasModifier(event) {
  return event.metaKey || event.ctrlKey || event.altKey
}
