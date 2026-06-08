"""S04 — pure rules: classify_cost, within_horizon, rank (free-first)."""
from datetime import datetime, timedelta, timezone

from events_parser.models import Event
from events_parser.rules import classify_cost, rank, within_horizon

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


def _ev(**kw):
    base = dict(title="E", host="H", domain="ai")
    base.update(kw)
    return Event(**base)


# --- classify_cost ---

def test_explicit_free_or_paid_is_kept():
    assert classify_cost(_ev(cost_status="free")) == "free"
    assert classify_cost(_ev(cost_status="paid")) == "paid"


def test_free_inferred_from_text_when_unknown():
    assert classify_cost(_ev(cost_status="unknown", price_note="Вход свободный")) == "free"
    assert classify_cost(_ev(cost_status="unknown", description="Участие бесплатное")) == "free"


def test_paid_inferred_from_price_signal():
    assert classify_cost(_ev(cost_status="unknown", price_note="5 000 ₽")) == "paid"
    assert classify_cost(_ev(cost_status="unknown", description="Билеты от 2000 руб.")) == "paid"


def test_unknown_when_no_signal():
    assert classify_cost(_ev(cost_status="unknown")) == "unknown"


# --- within_horizon ---

def test_undated_event_is_open():
    assert within_horizon(_ev(start_date=None), NOW) == "open"


def test_past_event_excluded():
    assert within_horizon(_ev(start_date=NOW - timedelta(days=1)), NOW) is False


def test_today_and_window_edges():
    assert within_horizon(_ev(start_date=NOW), NOW) is True
    assert within_horizon(_ev(start_date=NOW + timedelta(days=28)), NOW, horizon_days=28) is True
    assert within_horizon(_ev(start_date=NOW + timedelta(days=29)), NOW, horizon_days=28) is False


# --- rank (free before paid before unknown, then date asc) ---

def test_rank_orders_free_first_then_by_date():
    paid_soon = _ev(title="paid_soon", cost_status="paid", start_date=NOW + timedelta(days=2))
    free_late = _ev(title="free_late", cost_status="free", start_date=NOW + timedelta(days=10))
    free_soon = _ev(title="free_soon", cost_status="free", start_date=NOW + timedelta(days=3))
    unknown = _ev(title="unknown", cost_status="unknown", start_date=NOW + timedelta(days=1))

    ordered = [e.title for e in rank([paid_soon, free_late, free_soon, unknown])]
    assert ordered == ["free_soon", "free_late", "paid_soon", "unknown"]


def test_rank_is_stable_for_equal_keys():
    a = _ev(title="a", cost_status="free", start_date=NOW + timedelta(days=5))
    b = _ev(title="b", cost_status="free", start_date=NOW + timedelta(days=5))
    assert [e.title for e in rank([a, b])] == ["a", "b"]
