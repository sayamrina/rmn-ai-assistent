"""E-mails become checked drafts; nothing is booked before a person approves."""
from tests.conftest import next_weekday


def mail_id(client, subject):
    return next(m["id"] for m in client.get("/api/inbox").json() if m["subject"] == subject)


def test_reservation_mail_becomes_draft_and_is_booked_only_after_approval(client):
    mid = mail_id(client, "Tischreservierung Samstag")
    result = client.post(f"/api/inbox/{mid}/process").json()["result"]
    assert result["extracted"]["day"] == next_weekday(5).isoformat()
    assert result["extracted"]["time"] == "19:00" and result["extracted"]["persons"] == 6
    assert "Gado-Gado" in result["draft"] and "Erdnüsse enthalten" in result["draft"]
    before = len(client.get("/api/reservations").json())
    assert client.post(f"/api/inbox/{mid}/approve", json={}).status_code == 200
    assert len(client.get("/api/reservations").json()) == before + 1


def test_monday_request_gets_an_alternative(client):
    mid = mail_id(client, "Reservierung Montag")
    result = client.post(f"/api/inbox/{mid}/process").json()["result"]
    assert "Ruhetag" in result["draft"] and "Alternativvorschlag" in result["draft"]
    assert result["action"] is None


def test_catering_price_is_computed_from_the_price_list(client):
    mid = mail_id(client, "Catering für unsere Teamfeier")
    result = client.post(f"/api/inbox/{mid}/process").json()["result"]
    assert result["action"] == {"type": "catering_offer", "total": 630.0, "persons": 30, "variant": "vegetarisch"}
    assert "630,00 €" in result["draft"]


def test_api_basics(client):
    assert client.get("/api/meta").json()["mode"] == "demo"
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/stock/unbekannt/bookings", json={"change": 1, "reason": "x"}).status_code == 404
    po = client.post("/api/purchase-orders", json={"supplier_id": "frische"})
    assert po.status_code == 201 and po.json()["status"] == "Entwurf"
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert "Bestellentwurf erstellt" in actions
