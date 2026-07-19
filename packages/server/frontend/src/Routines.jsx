import { useCallback, useEffect, useState } from 'react'

import {
  createRoutine,
  deleteRoutine,
  getRoutines,
  updateRoutine,
} from './api.js'

const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

// The recurrence picker: one mode, one obvious input each. Shared by the create
// bar and the per-routine edit form, so both build the exact same payload.
function RoutineForm({ initial, vocab, submitLabel, onSubmit, onCancel }) {
  const [title, setTitle] = useState(initial?.title || '')
  const [freq, setFreq] = useState(initial?.freq || 'days')
  const [interval, setIntervalDays] = useState(initial?.interval || 3)
  const [weekdays, setWeekdays] = useState(initial?.weekdays || ['mon'])
  const [monthday, setMonthday] = useState(initial?.monthday || 1)
  const [month, setMonth] = useState(initial?.month || 1)
  const [day, setDay] = useState(initial?.day || 1)
  const [context, setContext] = useState(initial?.context || '')
  const [area, setArea] = useState(initial?.area || '')
  const [lead, setLead] = useState(initial?.lead || 0)
  const [busy, setBusy] = useState(false)

  function toggleWeekday(d) {
    setWeekdays((cur) =>
      cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d],
    )
  }

  async function submit(event) {
    event.preventDefault()
    const text = title.trim()
    if (!text || busy) return
    if (freq === 'weekly' && weekdays.length === 0) return
    setBusy(true)
    try {
      const fields = {
        title: text,
        freq,
        context: context || null,
        area: area || null,
        lead: Number(lead) || 0,
      }
      if (freq === 'days') fields.interval = Number(interval) || 1
      else if (freq === 'weekly') fields.weekdays = weekdays
      else if (freq === 'monthly') fields.monthday = Number(monthday) || 1
      else {
        fields.month = Number(month) || 1
        fields.day = Number(day) || 1
      }
      await onSubmit(fields)
      if (!initial) setTitle('') // create bar clears; edit form closes instead
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="routine-create" onSubmit={submit}>
      <input
        className="routine-title"
        type="text"
        placeholder="New routine (e.g. Water the plants)…"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        aria-label="Routine title"
      />

      <div className="routine-fields">
        <label>
          Repeats
          <select value={freq} onChange={(e) => setFreq(e.target.value)}>
            <option value="days">Every N days</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="yearly">Yearly</option>
          </select>
        </label>

        {freq === 'days' && (
          <label>
            Every … days
            <input
              type="number"
              min="1"
              value={interval}
              onChange={(e) => setIntervalDays(e.target.value)}
            />
          </label>
        )}

        {freq === 'weekly' && (
          <div className="weekday-picker" role="group" aria-label="Weekdays">
            {WEEKDAYS.map((d) => (
              <button
                key={d}
                type="button"
                className={`seg${weekdays.includes(d) ? ' active' : ''}`}
                onClick={() => toggleWeekday(d)}
              >
                {d[0].toUpperCase() + d.slice(1)}
              </button>
            ))}
          </div>
        )}

        {freq === 'monthly' && (
          <label>
            On day
            <input
              type="number"
              min="1"
              max="31"
              value={monthday}
              onChange={(e) => setMonthday(e.target.value)}
            />
          </label>
        )}

        {freq === 'yearly' && (
          <>
            <label>
              Month
              <select value={month} onChange={(e) => setMonth(e.target.value)}>
                {MONTHS.map((m, i) => (
                  <option key={m} value={i + 1}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Day
              <input
                type="number"
                min="1"
                max="31"
                value={day}
                onChange={(e) => setDay(e.target.value)}
              />
            </label>
          </>
        )}

        <label>
          Context
          <select value={context} onChange={(e) => setContext(e.target.value)}>
            <option value="">(none)</option>
            {vocab.contexts.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Area
          <select value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">(none)</option>
            {vocab.areas.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label>
          Notify … days before
          <input
            type="number"
            min="0"
            value={lead}
            onChange={(e) => setLead(e.target.value)}
          />
        </label>
      </div>

      <div className="routine-actions">
        <button type="submit" className="primary" disabled={busy || !title.trim()}>
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}

function RoutineRow({ routine, vocab, onChanged }) {
  const [editing, setEditing] = useState(false)

  async function save(fields) {
    await updateRoutine(routine.id, fields)
    setEditing(false)
    onChanged()
  }

  async function remove() {
    await deleteRoutine(routine.id)
    onChanged()
  }

  async function togglePaused() {
    await updateRoutine(routine.id, { active: !routine.active })
    onChanged()
  }

  if (editing) {
    return (
      <li className="routine editing">
        <RoutineForm
          initial={routine}
          vocab={vocab}
          submitLabel="Save"
          onSubmit={save}
          onCancel={() => setEditing(false)}
        />
      </li>
    )
  }

  return (
    <li className={`routine${routine.active ? '' : ' paused'}`}>
      <span className="routine-badge">⟳</span>
      <span className="todo-title">{routine.title}</span>
      <span className="tag">{routine.rule}</span>
      {routine.lead > 0 && <span className="tag">{routine.lead}d before</span>}
      {routine.context && <span className="tag context">{routine.context}</span>}
      {routine.area && <span className="tag area">{routine.area}</span>}
      {routine.next_due && <span className="tag date">next {routine.next_due}</span>}
      <button
        className="today-toggle"
        type="button"
        title={routine.active ? 'Pause this routine' : 'Resume this routine'}
        onClick={togglePaused}
      >
        {routine.active ? '❚❚ Pause' : '▶ Resume'}
      </button>
      <button
        className="row-edit"
        type="button"
        title="Edit routine"
        aria-label={`Edit ${routine.title}`}
        onClick={() => setEditing(true)}
      >
        ✎
      </button>
      <button
        className="row-del"
        type="button"
        title="Delete routine"
        aria-label={`Delete ${routine.title}`}
        onClick={remove}
      >
        ✕
      </button>
    </li>
  )
}

// The routines view: define recurring todos, see when each next fires, edit or
// pause them.
export default function Routines({ vocab, onChanged }) {
  const [routines, setRoutines] = useState([])
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setRoutines(await getRoutines())
  }, [])

  useEffect(() => {
    load().catch((e) => setError(String(e)))
  }, [load])

  const afterChange = () => {
    load().catch((e) => setError(String(e)))
    onChanged()
  }

  return (
    <div className="routines">
      <RoutineForm
        vocab={vocab}
        submitLabel="Create routine"
        onSubmit={async (fields) => {
          await createRoutine(fields)
          afterChange()
        }}
      />
      {error && <p className="error">{error}</p>}
      {routines.length === 0 ? (
        <p className="empty">No routines yet.</p>
      ) : (
        <ul className="routine-list">
          {routines.map((r) => (
            <RoutineRow
              key={r.id}
              routine={r}
              vocab={vocab}
              onChanged={afterChange}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
