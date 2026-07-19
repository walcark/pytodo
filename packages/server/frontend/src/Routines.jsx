import { useCallback, useEffect, useState } from 'react'

import { createRoutine, deleteRoutine, getRoutines } from './api.js'

const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

// The recurrence picker: one mode, one obvious input each. It builds the exact
// payload the API expects (only the fields the chosen freq needs).
function CreateRoutine({ vocab, onCreated }) {
  const [title, setTitle] = useState('')
  const [freq, setFreq] = useState('days')
  const [interval, setIntervalDays] = useState(3)
  const [weekdays, setWeekdays] = useState(['mon'])
  const [monthday, setMonthday] = useState(1)
  const [month, setMonth] = useState(1)
  const [day, setDay] = useState(1)
  const [context, setContext] = useState('')
  const [area, setArea] = useState('')
  const [lead, setLead] = useState(0)
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
      await createRoutine(fields)
      setTitle('')
      onCreated()
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

      <button type="submit" className="primary" disabled={busy || !title.trim()}>
        Create routine
      </button>
    </form>
  )
}

// The routines view: define recurring todos and see when each next fires.
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

  async function remove(id) {
    await deleteRoutine(id)
    afterChange()
  }

  return (
    <div className="routines">
      <CreateRoutine vocab={vocab} onCreated={afterChange} />
      {error && <p className="error">{error}</p>}
      {routines.length === 0 ? (
        <p className="empty">No routines yet.</p>
      ) : (
        <ul className="routine-list">
          {routines.map((r) => (
            <li key={r.id} className="routine">
              <span className="routine-badge">⟳</span>
              <span className="todo-title">{r.title}</span>
              <span className="tag">{r.rule}</span>
              {r.lead > 0 && <span className="tag">{r.lead}d before</span>}
              {r.context && <span className="tag context">{r.context}</span>}
              {r.area && <span className="tag area">{r.area}</span>}
              {r.next_due && <span className="tag date">next {r.next_due}</span>}
              <button
                className="row-del"
                type="button"
                title="Delete routine"
                aria-label={`Delete ${r.title}`}
                onClick={() => remove(r.id)}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
