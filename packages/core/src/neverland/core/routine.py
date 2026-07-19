"""Recurring routines: templates that spawn ordinary todos on a schedule.

A routine is not a special kind of todo, it is a *generator*. It holds a
recurrence rule and a single ``next_due`` date; when that date arrives it
materializes a normal todo (carrying ``routine: <id>``), which then lives and
dies like any other (into ``done/``, into history). The reference points one
way only, routine -> occurrence via the todo's ``routine`` field, so deleting
the routine never dangles.

This is the GTD tickler, not a deadline: the date says "when should this come
back", not "when is it due to the outside world" (see ``docs/model.md``). Four
shapes cover the real cases:

- ``days``    : a fixed cadence, every N days ("water the plants, every 3 days")
- ``weekly``  : given weekdays ("run on Mon, Wed, Sat")
- ``monthly`` : a day of the month ("review the bank account on the 1st")
- ``yearly``  : a month and day ("call Marie on June 3")

Each shape answers the same two questions, so the rest of the system only ever
touches ``next_due`` and :meth:`Recurrence.next_after`.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path

import yaml

# date.weekday(): Monday is 0, Sunday is 6. Same order here.
WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_WEEKDAY_INDEX = {name: i for i, name in enumerate(WEEKDAY_NAMES)}

# Only used to render a rule for humans (``describe``).
MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


class Freq(Enum):
    """The four recurrence shapes."""

    DAYS = "days"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


def _clamped(year: int, month: int, day: int) -> date:
    """Return ``date(year, month, day)`` with ``day`` clamped to the month length.

    So "the 31st" lands on the 28th/30th where the month is shorter, and a Feb
    29 anniversary falls back to Feb 28 in common years.
    """
    last = monthrange(year, month)[1]
    return date(year, month, min(day, last))


@dataclass
class Recurrence:
    """A recurrence rule: a :class:`Freq` and the parameter that shape needs.

    Attributes
    ----------
    freq : Freq
        Which shape applies.
    interval : int
        For ``days``: the number of days between occurrences.
    weekdays : list of int
        For ``weekly``: weekday indices (Monday is 0), e.g. ``[0, 2, 5]``.
    monthday : int or None
        For ``monthly``: the day of the month (clamped to the month length).
    month : int or None
        For ``yearly``: the month (1-12).
    day : int or None
        For ``yearly``: the day of that month (clamped in February).
    """

    freq: Freq
    interval: int = 1
    weekdays: list[int] = field(default_factory=list)
    monthday: int | None = None
    month: int | None = None
    day: int | None = None

    # -- Scheduling -------------------------------------------------------

    def matches(self, d: date) -> bool:
        """Return whether ``d`` is itself an occurrence (calendar shapes only).

        ``days`` has no per-date predicate (it is a cadence, not a calendar
        rule), so it never "matches": seeding uses ``d`` directly instead.
        """
        if self.freq is Freq.WEEKLY:
            return d.weekday() in self.weekdays
        if self.freq is Freq.MONTHLY:
            return d == _clamped(d.year, d.month, self.monthday or 1)
        if self.freq is Freq.YEARLY:
            return d == _clamped(d.year, self.month or 1, self.day or 1)
        return False

    def next_after(self, d: date) -> date:
        """Return the first occurrence strictly after ``d``."""
        if self.freq is Freq.DAYS:
            return d + timedelta(days=max(self.interval, 1))
        if self.freq is Freq.WEEKLY:
            for offset in range(1, 8):
                cand = d + timedelta(days=offset)
                if cand.weekday() in self.weekdays:
                    return cand
            raise ValueError("weekly recurrence has no weekdays")
        if self.freq is Freq.MONTHLY:
            dom = self.monthday or 1
            year, month = d.year, d.month
            for _ in range(2):
                cand = _clamped(year, month, dom)
                if cand > d:
                    return cand
                month += 1
                if month > 12:
                    month, year = 1, year + 1
            return _clamped(year, month, dom)
        # yearly
        m, dom = self.month or 1, self.day or 1
        cand = _clamped(d.year, m, dom)
        return cand if cand > d else _clamped(d.year + 1, m, dom)

    def first_on_or_after(self, d: date) -> date:
        """Return the first occurrence on or after ``d`` (used to seed a routine)."""
        if self.freq is Freq.DAYS:
            return d
        return d if self.matches(d) else self.next_after(d)

    def describe(self) -> str:
        """Return a short human-readable rule (for the UI)."""
        if self.freq is Freq.DAYS:
            n = max(self.interval, 1)
            return "every day" if n == 1 else f"every {n} days"
        if self.freq is Freq.WEEKLY:
            names = (WEEKDAY_NAMES[i].capitalize() for i in sorted(self.weekdays))
            return f"weekly: {', '.join(names)}"
        if self.freq is Freq.MONTHLY:
            return f"monthly on day {self.monthday}"
        return f"yearly on {MONTH_NAMES[(self.month or 1) - 1]} {self.day}"

    # -- Serialization ----------------------------------------------------

    def to_dict(self) -> dict:
        """Return the rule as a plain mapping for the front matter."""
        data: dict = {"freq": self.freq.value}
        if self.freq is Freq.DAYS:
            data["interval"] = self.interval
        elif self.freq is Freq.WEEKLY:
            data["weekdays"] = [WEEKDAY_NAMES[i] for i in self.weekdays]
        elif self.freq is Freq.MONTHLY:
            data["monthday"] = self.monthday
        else:
            data["month"] = self.month
            data["day"] = self.day
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Recurrence:
        """Parse a rule from its front-matter mapping.

        Raises
        ------
        ValueError
            If the frequency is unknown or its parameters are missing/invalid.
        """
        freq = Freq(str(data.get("freq")))
        if freq is Freq.DAYS:
            interval = int(data.get("interval", 1))
            if interval < 1:
                raise ValueError("interval must be >= 1")
            return cls(freq=freq, interval=interval)
        if freq is Freq.WEEKLY:
            names = data.get("weekdays") or []
            weekdays = sorted({_WEEKDAY_INDEX[str(n).lower()] for n in names})
            if not weekdays:
                raise ValueError("weekly recurrence needs at least one weekday")
            return cls(freq=freq, weekdays=weekdays)
        if freq is Freq.MONTHLY:
            monthday = int(data.get("monthday") or 0)
            if not 1 <= monthday <= 31:
                raise ValueError("monthday must be between 1 and 31")
            return cls(freq=freq, monthday=monthday)
        month = int(data.get("month") or 0)
        day = int(data.get("day") or 0)
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            raise ValueError("yearly recurrence needs a valid month and day")
        return cls(freq=freq, month=month, day=day)


@dataclass
class Routine:
    """A recurring template, stored as one markdown file under ``routines/``.

    Attributes
    ----------
    id : str
        Unique identifier, also the file stem. Occurrences reference it via
        their ``routine`` field.
    title : str
        Title given to each spawned todo.
    recurrence : Recurrence
        The schedule.
    context, area, project : str or None
        Copied onto each occurrence, so a routine can be actionable the moment
        it appears (a ``next`` todo with a context).
    lead : int
        How many days before ``next_due`` the occurrence should appear (0 = on
        the day). Useful for yearly/monthly ("buy the gift 5 days before").
    next_due : datetime.date or None
        The next date this routine is due; the single value scheduling reads.
    active : bool
        A paused routine spawns nothing.
    body : str
        Optional notes.
    path : pathlib.Path or None
        On-disk location, when known.
    """

    id: str
    title: str
    recurrence: Recurrence
    context: str | None = None
    area: str | None = None
    project: str | None = None
    lead: int = 0
    next_due: date | None = None
    active: bool = True
    body: str = ""
    path: Path | None = None

    def due_on(self, day: date) -> bool:
        """Return whether the occurrence should appear on ``day`` (lead included)."""
        if not self.active or self.next_due is None:
            return False
        return self.next_due - timedelta(days=self.lead) <= day

    def advance(self, after: date) -> None:
        """Move ``next_due`` to the first occurrence strictly after ``after``.

        Called when an occurrence is resolved (completed or deleted): the next
        due date is computed from the rule, skipping anything already past so a
        long absence never backfills a pile of missed occurrences.
        """
        if self.next_due is None:
            self.next_due = self.recurrence.first_on_or_after(after + timedelta(days=1))
            return
        nd = self.recurrence.next_after(self.next_due)
        while nd <= after:
            nd = self.recurrence.next_after(nd)
        self.next_due = nd

    # -- Serialization ----------------------------------------------------

    def to_frontmatter(self) -> dict:
        """Return the front matter as an ordered mapping."""
        return {
            "title": self.title,
            "recurrence": self.recurrence.to_dict(),
            "context": self.context,
            "area": self.area,
            "project": self.project,
            "lead": self.lead,
            "next_due": self.next_due,
            "active": self.active,
        }

    def to_markdown(self) -> str:
        """Render the routine as a markdown document."""
        fm = yaml.safe_dump(
            self.to_frontmatter(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ).rstrip("\n")
        body = self.body.strip("\n")
        text = f"---\n{fm}\n---\n"
        if body:
            text += f"\n{body}\n"
        return text

    def require_path(self) -> Path:
        """Return the on-disk path, raising if it is unset or missing."""
        if self.path is None or not self.path.exists():
            raise FileNotFoundError(f"routine not found: {self.id}")
        return self.path


def _coerce_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def parse_markdown(text: str, *, routine_id: str, path: Path | None = None) -> Routine:
    """Parse a routine file into a :class:`Routine`.

    Raises
    ------
    ValueError
        If the front matter is missing, malformed, or lacks a title/recurrence.
    """
    if not text.startswith("---"):
        raise ValueError("missing front matter (file must start with '---')")

    parts = text.split("\n")
    if parts[0].strip() != "---":
        raise ValueError("malformed front matter")
    end = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("unterminated front matter (missing closing '---')")

    fm = yaml.safe_load("\n".join(parts[1:end])) or {}
    body = "\n".join(parts[end + 1 :]).strip("\n")

    title = fm.get("title")
    if not title:
        raise ValueError("mandatory 'title' field is missing")
    recurrence = Recurrence.from_dict(fm.get("recurrence") or {})

    return Routine(
        id=routine_id,
        title=str(title),
        recurrence=recurrence,
        context=(fm.get("context") or None),
        area=(fm.get("area") or None),
        project=(fm.get("project") or None),
        lead=int(fm.get("lead") or 0),
        next_due=_coerce_date(fm.get("next_due")),
        active=bool(fm.get("active", True)),
        body=body,
        path=path,
    )


def load_routine(path: Path) -> Routine:
    """Read and parse a routine file from disk."""
    return parse_markdown(
        path.read_text(encoding="utf-8"), routine_id=path.stem, path=path
    )
