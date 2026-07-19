from datetime import date

import pytest

from neverland.core.routine import Freq, Recurrence


def _days(n):
    return Recurrence(freq=Freq.DAYS, interval=n)


def _weekly(*names):
    idx = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    return Recurrence(freq=Freq.WEEKLY, weekdays=sorted(idx[n] for n in names))


def test_days_is_a_fixed_gap():
    r = _days(3)
    assert r.next_after(date(2026, 7, 1)) == date(2026, 7, 4)
    assert r.first_on_or_after(date(2026, 7, 1)) == date(2026, 7, 1)


def test_weekly_finds_next_matching_weekday():
    r = _weekly("mon", "wed", "sat")  # Jul 1 2026 is a Wednesday
    wed = date(2026, 7, 1)
    assert r.matches(wed) is True
    assert r.next_after(wed) == date(2026, 7, 4)  # Saturday
    assert r.next_after(date(2026, 7, 4)) == date(2026, 7, 6)  # Monday
    assert r.first_on_or_after(date(2026, 6, 30)) == wed  # Tue -> next Wed


def test_monthly_lands_on_the_day_and_clamps():
    r = Recurrence(freq=Freq.MONTHLY, monthday=31)
    # from mid-July, next 31st is Jul 31; then Aug 31; then clamps in Sept (30)
    assert r.next_after(date(2026, 7, 15)) == date(2026, 7, 31)
    assert r.next_after(date(2026, 7, 31)) == date(2026, 8, 31)
    assert r.next_after(date(2026, 8, 31)) == date(2026, 9, 30)


def test_yearly_repeats_and_clamps_feb_29():
    r = Recurrence(freq=Freq.YEARLY, month=6, day=3)
    assert r.next_after(date(2026, 6, 3)) == date(2027, 6, 3)
    assert r.first_on_or_after(date(2026, 1, 1)) == date(2026, 6, 3)

    leap = Recurrence(freq=Freq.YEARLY, month=2, day=29)
    # 2027 is not a leap year -> clamps to Feb 28
    assert leap.next_after(date(2026, 3, 1)) == date(2027, 2, 28)


def test_from_dict_round_trip_and_validation():
    for rule in (
        _days(3),
        _weekly("mon", "fri"),
        Recurrence(freq=Freq.MONTHLY, monthday=1),
        Recurrence(freq=Freq.YEARLY, month=12, day=25),
    ):
        assert Recurrence.from_dict(rule.to_dict()) == rule

    with pytest.raises(ValueError):
        Recurrence.from_dict({"freq": "weekly", "weekdays": []})
    with pytest.raises(ValueError):
        Recurrence.from_dict({"freq": "monthly", "monthday": 0})
    with pytest.raises(ValueError):
        Recurrence.from_dict({"freq": "nope"})
