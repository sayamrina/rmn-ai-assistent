"""Business rules are computed in code: order quantities, approval limits, opening hours and capacity."""
import pytest

from app.tools import Tools
from tests.conftest import next_weekday


def test_purchase_proposal_fills_up_to_twice_the_minimum_in_full_packs(db):
    orders = {o["supplier_id"]: o for o in Tools(db).propose_purchase_order()["orders"]}
    coconut = next(line for line in orders["asia"]["lines"] if line["ingredient"] == "Kokosmilch")
    assert coconut["quantity"] == 48  # stock 8, target 48 -> 40 needed -> 4 packs of 12
    assert orders["asia"]["below_min_order"] is True  # 134 € < 150 € minimum order
    assert orders["halal"]["total"] == 151.2


def test_order_over_500_needs_approval(db):
    db.execute("UPDATE ingredients SET stock = 0, min_stock = 20 WHERE id = 'rind'")  # e.g. before a large catering
    t = Tools(db)
    po = t.create_purchase_order("halal")
    assert po["needs_approval"] and po["total"] > 500
    with pytest.raises(PermissionError):
        t.send_purchase_order(po["id"])
    assert t.send_purchase_order(po["id"], approved=True)["status"].startswith("An Lieferant")


def test_stock_cannot_go_negative(db):
    with pytest.raises(ValueError):
        Tools(db).book_stock("tempeh", -10, "Verbrauch")


def test_capacity_counts_overlapping_reservations(db):
    sat = next_weekday(5).isoformat()
    t = Tools(db)
    # 40 seats - 10 walk-in - 24 already booked between 17:00 and 21:00
    assert t.check_availability(sat, "19:00", 6)["possible"]
    assert not t.check_availability(sat, "19:00", 7)["possible"]
    assert t.check_availability(sat, "12:00", 12)["possible"]


def test_opening_hours_and_group_size(db):
    t = Tools(db)
    assert "Ruhetag" in t.check_availability(next_weekday(0).isoformat(), "19:00", 2)["reason"]
    assert not t.check_availability(next_weekday(2).isoformat(), "15:00", 2)["possible"]
    assert not t.check_availability(next_weekday(2).isoformat(), "19:00", 14)["possible"]
