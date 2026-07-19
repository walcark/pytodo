const FIXED_VIEWS = [
  { value: 'inbox', label: 'Inbox', icon: '\u{1F4E5}' },
  { value: 'today', label: 'Today', icon: '☀️' },
  { value: 'all', label: 'All', icon: '\u{1F5C2}️' },
  { value: 'review', label: 'Review', icon: '\u{1FA79}' },
  { value: 'history', label: 'History', icon: '\u{1F4D3}' },
]

const LIST_VIEWS = [
  { value: 'next', label: 'Next', icon: '▶' },
  { value: 'waiting', label: 'Waiting', icon: '⏳' },
  { value: 'someday', label: 'Someday', icon: '\u{1F4AD}' },
]

function isActive(selection, kind, value) {
  return selection.kind === kind && selection.value === value
}

function Item({ icon, label, count, active, onClick }) {
  return (
    <button
      className={`nav-item${active ? ' active' : ''}`}
      onClick={onClick}
      type="button"
    >
      {icon && <span className="nav-icon">{icon}</span>}
      <span className="nav-label">{label}</span>
      {count > 0 && <span className="nav-count">{count}</span>}
    </button>
  )
}

export default function Sidebar({ views, vocab, selection, onSelect }) {
  const count = (key) => (views ? views[key] : 0)
  const namedCount = (list, name) => {
    const found = (list || []).find((entry) => entry.name === name)
    return found ? found.count : 0
  }

  return (
    <nav className="sidebar">
      <div className="brand">neverland</div>

      <div className="nav-group">
        {FIXED_VIEWS.map((v) => (
          <Item
            key={v.value}
            icon={v.icon}
            label={v.label}
            count={count(v.value)}
            active={isActive(selection, 'view', v.value)}
            onClick={() => onSelect({ kind: 'view', value: v.value, label: v.label })}
          />
        ))}
      </div>

      <div className="nav-group">
        <div className="nav-title">Lists</div>
        {LIST_VIEWS.map((v) => (
          <Item
            key={v.value}
            icon={v.icon}
            label={v.label}
            count={count(v.value)}
            active={isActive(selection, 'view', v.value)}
            onClick={() => onSelect({ kind: 'view', value: v.value, label: v.label })}
          />
        ))}
      </div>

      <div className="nav-group">
        <div className="nav-title">Areas</div>
        {vocab.areas.map((area) => (
          <Item
            key={area}
            label={area}
            count={namedCount(views && views.areas, area)}
            active={isActive(selection, 'area', area)}
            onClick={() => onSelect({ kind: 'area', value: area, label: area })}
          />
        ))}
      </div>

      <div className="nav-group">
        <div className="nav-title">Contexts</div>
        {vocab.contexts.map((context) => (
          <Item
            key={context}
            label={context}
            count={namedCount(views && views.contexts, context)}
            active={isActive(selection, 'context', context)}
            onClick={() =>
              onSelect({ kind: 'context', value: context, label: context })
            }
          />
        ))}
      </div>
    </nav>
  )
}
