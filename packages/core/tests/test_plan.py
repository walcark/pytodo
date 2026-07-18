from datetime import date

from neverland.core import store
from neverland.core.plan import DayPlan, PlanEntry, PlanStatus, parse_plan
from neverland.core.store import PLANS_DIRNAME


def _plan() -> DayPlan:
    return DayPlan(
        day=date(2026, 7, 15),
        entries=[
            PlanEntry("20260705-143201-a3f2", "Renew passport"),
            PlanEntry("20260706-091200-b1c3", "Write report", PlanStatus.DOING),
            PlanEntry("20260701-120000-77de", "Pay bill", PlanStatus.DONE),
        ],
    )


def test_markdown_roundtrip():
    plan = _plan()
    reparsed = parse_plan(plan.to_markdown(), day=plan.day)
    assert reparsed.day == plan.day
    assert [(e.todo_id, e.title, e.status) for e in reparsed.entries] == [
        (e.todo_id, e.title, e.status) for e in plan.entries
    ]


def test_checkbox_marks():
    md = _plan().to_markdown()
    assert "- [ ] 20260705-143201-a3f2  Renew passport" in md
    assert "- [/] 20260706-091200-b1c3  Write report" in md
    assert "- [x] 20260701-120000-77de  Pay bill" in md


def test_unknown_mark_falls_back_to_planned():
    plan = parse_plan(
        "---\ndate: 2026-07-15\n---\n- [?] id42  Mystery\n", day=date(2026, 7, 15)
    )
    assert plan.entries[0].status is PlanStatus.PLANNED


def test_find_and_has():
    plan = _plan()
    assert plan.has("20260706-091200-b1c3")
    assert not plan.has("nope")
    assert plan.find("20260701-120000-77de").title == "Pay bill"
    assert plan.find("nope") is None


def test_load_missing_plan_is_empty(tmp_path):
    plan = store.load_day_plan(tmp_path, date(2026, 7, 15))
    assert plan.entries == []
    assert not store.plan_exists(tmp_path, date(2026, 7, 15))


def test_save_and_load(tmp_path):
    store.save_day_plan(tmp_path, _plan())
    assert store.plan_exists(tmp_path, date(2026, 7, 15))
    assert (tmp_path / PLANS_DIRNAME / "2026-07-15.md").exists()
    loaded = store.load_day_plan(tmp_path, date(2026, 7, 15))
    assert len(loaded.entries) == 3
    assert loaded.entries[1].status is PlanStatus.DOING


def test_list_plan_days_sorted(tmp_path):
    for d in (date(2026, 7, 15), date(2026, 7, 10), date(2026, 7, 12)):
        store.save_day_plan(tmp_path, DayPlan(day=d, entries=[PlanEntry("x", "t")]))
    assert store.list_plan_days(tmp_path) == [
        date(2026, 7, 10),
        date(2026, 7, 12),
        date(2026, 7, 15),
    ]


def test_latest_plan_before_skips_empty_and_future(tmp_path):
    store.save_day_plan(
        tmp_path, DayPlan(day=date(2026, 7, 10), entries=[PlanEntry("a", "A")])
    )
    store.save_day_plan(tmp_path, DayPlan(day=date(2026, 7, 12), entries=[]))  # empty
    store.save_day_plan(
        tmp_path, DayPlan(day=date(2026, 7, 20), entries=[PlanEntry("z", "Z")])
    )

    latest = store.latest_plan_before(tmp_path, date(2026, 7, 15))
    assert latest is not None
    assert latest.day == date(2026, 7, 10)  # 12 is empty, 20 is in the future


def test_latest_plan_before_none_when_no_history(tmp_path):
    assert store.latest_plan_before(tmp_path, date(2026, 7, 15)) is None
