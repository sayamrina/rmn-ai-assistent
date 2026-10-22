"""The actions the assistant may take. Each one is a plain function with a JSON schema, so the same code serves the
REST API, the rule-based demo and the language model's tool calls. Business rules (stock levels, opening hours,
capacity, order quantities) are decided here in code, never by the model.
"""
import json
import math
import re
from datetime import date, datetime, time, timedelta

from . import dates
from .config import settings
from .db import Database
from .knowledge import knowledge

# lunch and dinner service; reservations must end before kitchen close
OPENING = {  # weekday -> list of (open, last reservation)
    0: [],
    1: [(time(11, 30), time(13, 30)), (time(17, 30), time(21, 0))],
    2: [(time(11, 30), time(13, 30)), (time(17, 30), time(21, 0))],
    3: [(time(11, 30), time(13, 30)), (time(17, 30), time(21, 0))],
    4: [(time(11, 30), time(13, 30)), (time(17, 30), time(21, 0))],
    5: [(time(11, 30), time(13, 30)), (time(17, 30), time(21, 0))],
    6: [(time(12, 0), time(20, 0))],
}


class Tools:
    def __init__(self, db: Database):
        self.db = db

    # --- knowledge -------------------------------------------------------------------------------------------
    def search_documents(self, query: str) -> dict:
        hits = knowledge.search(query)
        return {"passages": [{"source": p.source, "text": p.text} for p, _ in hits],
                "found": bool(hits)}

    def menu_passages(self):
        return [p for p in knowledge.passages if p.doc == "speisekarte" and p.section not in ("Allgemein", "Getränke")]

    # --- stock (Warenwirtschaft) -----------------------------------------------------------------------------
    def _ingredient_row(self, r: dict) -> dict:
        return {"id": r["id"], "name": r["name"], "stock": r["stock"], "unit": r["unit"], "min_stock": r["min_stock"],
                "below_min": r["stock"] < r["min_stock"], "supplier": r["supplier_name"], "storage": r["storage"]}

    def list_stock(self) -> list[dict]:
        rows = self.db.query("SELECT i.*, s.name AS supplier_name FROM ingredients i JOIN suppliers s ON s.id = i.supplier_id "
                             "ORDER BY (i.stock < i.min_stock) DESC, i.name")
        return [self._ingredient_row(r) for r in rows]

    def find_ingredients(self, text: str) -> list[dict]:
        t = text.lower()
        out = []
        for r in self.db.query("SELECT i.*, s.name AS supplier_name FROM ingredients i JOIN suppliers s ON s.id = i.supplier_id"):
            names = [r["name"].lower().split(" (")[0]] + [a for a in r["aliases"].split(",") if a]
            if any(n and re.search(rf"\b{re.escape(n)}\b", t) for n in names):
                out.append(self._ingredient_row(r))
        return out

    def get_stock(self, ingredient: str) -> dict:
        found = self.find_ingredients(ingredient)
        return {"ingredients": found, "found": bool(found)}

    def low_stock(self) -> dict:
        items = [i for i in self.list_stock() if i["below_min"]]
        return {"ingredients": items, "count": len(items)}

    def book_stock(self, ingredient_id: str, change: float, reason: str, actor: str = "Personal") -> dict:
        row = self.db.query("SELECT stock FROM ingredients WHERE id = ?", (ingredient_id,))
        if not row:
            raise KeyError(ingredient_id)
        new = round(row[0]["stock"] + change, 2)
        if new < 0:
            raise ValueError("Bestand darf nicht negativ werden")
        self.db.execute("UPDATE ingredients SET stock = ? WHERE id = ?", (new, ingredient_id))
        self.db.audit(actor, "Bestand gebucht", {"zutat": ingredient_id, "änderung": change, "grund": reason, "neu": new})
        return {"id": ingredient_id, "stock": new}

    # --- purchasing --------------------------------------------------------------------------------------------
    def propose_purchase_order(self, supplier: str | None = None) -> dict:
        """Order everything below minimum up to the target stock (2 × minimum), rounded up to full packs."""
        rows = self.db.query("SELECT i.*, s.name AS supplier_name, s.min_order, s.delivery FROM ingredients i "
                             "JOIN suppliers s ON s.id = i.supplier_id WHERE i.stock < i.min_stock ORDER BY s.id, i.name")
        groups: dict[str, dict] = {}
        for r in rows:
            if supplier and supplier.lower() not in (r["supplier_id"], r["supplier_name"].lower()):
                continue
            packs = math.ceil((2 * r["min_stock"] - r["stock"]) / r["pack_size"])
            qty = round(packs * r["pack_size"], 2)
            g = groups.setdefault(r["supplier_id"], {"supplier_id": r["supplier_id"], "supplier": r["supplier_name"],
                                                     "delivery": r["delivery"], "min_order": r["min_order"], "lines": []})
            g["lines"].append({"ingredient": r["name"], "quantity": qty, "unit": r["unit"], "price": r["price"],
                               "total": round(qty * r["price"], 2)})
        for g in groups.values():
            g["total"] = round(sum(line["total"] for line in g["lines"]), 2)
            g["needs_approval"] = g["total"] > 500
            g["below_min_order"] = g["total"] < g["min_order"]
        return {"orders": list(groups.values())}

    def create_purchase_order(self, supplier_id: str, actor: str = "Personal") -> dict:
        proposal = self.propose_purchase_order(supplier_id)["orders"]
        if not proposal:
            raise ValueError("Für diesen Lieferanten liegt kein Artikel unter Mindestbestand.")
        p = proposal[0]
        status = "Freigabe durch Restaurantleitung nötig" if p["needs_approval"] else "Entwurf"
        po_id = self.db.execute("INSERT INTO purchase_orders (supplier_id, status, lines, total, needs_approval, created_at) "
                                "VALUES (?,?,?,?,?,?)", (supplier_id, status, json.dumps(p["lines"], ensure_ascii=False),
                                                         p["total"], int(p["needs_approval"]),
                                                         datetime.now().replace(microsecond=0).isoformat()))
        self.db.audit(actor, "Bestellentwurf erstellt", {"bestellung": po_id, "lieferant": p["supplier"], "summe": p["total"]})
        return self.get_purchase_order(po_id)

    def get_purchase_order(self, po_id: int) -> dict:
        r = self.db.query("SELECT p.*, s.name AS supplier, s.email, s.delivery FROM purchase_orders p "
                          "JOIN suppliers s ON s.id = p.supplier_id WHERE p.id = ?", (po_id,))
        if not r:
            raise KeyError(po_id)
        r = r[0]
        r["lines"] = json.loads(r["lines"])
        r["needs_approval"] = bool(r["needs_approval"])
        return r

    def list_purchase_orders(self) -> list[dict]:
        return [self.get_purchase_order(r["id"]) for r in self.db.query("SELECT id FROM purchase_orders ORDER BY id DESC")]

    def send_purchase_order(self, po_id: int, approved: bool = False, actor: str = "Personal") -> dict:
        po = self.get_purchase_order(po_id)
        if po["status"].startswith("An Lieferant"):
            return po
        if po["needs_approval"] and not approved:
            raise PermissionError("Bestellungen über 500 € gibt die Restaurantleitung frei.")
        self.db.execute("UPDATE purchase_orders SET status = ? WHERE id = ?",
                        ("An Lieferant übermittelt (Demo, keine echte E-Mail)", po_id))
        self.db.audit(actor, "Bestellung übermittelt", {"bestellung": po_id, "an": po["email"], "summe": po["total"]})
        return self.get_purchase_order(po_id)

    # --- reservations ------------------------------------------------------------------------------------------
    def check_availability(self, day: str, at: str, persons: int) -> dict:
        d, t = date.fromisoformat(day), time.fromisoformat(at)
        result = {"day": day, "day_label": dates.fmt_date(d), "time": at, "persons": persons}
        if d < dates.today():
            return {**result, "possible": False, "reason": "Das Datum liegt in der Vergangenheit."}
        slots = OPENING[d.weekday()]
        if not slots:
            return {**result, "possible": False, "reason": "Montag ist Ruhetag."}
        if not any(a <= t <= b for a, b in slots):
            times = " und ".join(f"{a.strftime('%H:%M')} bis {b.strftime('%H:%M')} Uhr" for a, b in slots)
            return {**result, "possible": False, "reason": f"Reservierungen sind an diesem Tag von {times} möglich."}
        if persons > settings.max_group:
            return {**result, "possible": False,
                    "reason": f"Gruppen über {settings.max_group} Personen nur nach Absprache mit der Restaurantleitung."}
        start = datetime.combine(d, t)
        booked = 0
        for r in self.db.query("SELECT time, persons FROM reservations WHERE day = ?", (day,)):
            other = datetime.combine(d, time.fromisoformat(r["time"]))
            if abs((other - start).total_seconds()) < 2 * 3600:  # tables are held for about two hours
                booked += r["persons"]
        free = settings.seats - settings.walk_in_reserve - booked
        possible = persons <= free
        reason = (f"Noch {free} Plätze für Reservierungen frei." if possible
                  else f"Zu dieser Zeit sind nur noch {max(free, 0)} Plätze für Reservierungen frei.")
        return {**result, "possible": possible, "free_seats": max(free, 0), "reason": reason}

    def list_reservations(self, day: str | None = None) -> list[dict]:
        if day:
            return self.db.query("SELECT * FROM reservations WHERE day = ? ORDER BY time", (day,))
        return self.db.query("SELECT * FROM reservations WHERE day >= ? ORDER BY day, time", (dates.today().isoformat(),))

    def add_reservation(self, name: str, day: str, at: str, persons: int, notes: str, source: str, actor: str) -> dict:
        check = self.check_availability(day, at, persons)
        if not check["possible"]:
            raise ValueError(check["reason"])
        rid = self.db.execute("INSERT INTO reservations (name, day, time, persons, notes, source) VALUES (?,?,?,?,?,?)",
                              (name, day, at, persons, notes, source))
        self.db.audit(actor, "Reservierung eingetragen", {"id": rid, "name": name, "tag": day, "zeit": at, "personen": persons})
        return self.db.query("SELECT * FROM reservations WHERE id = ?", (rid,))[0]


# schemas for the language model (OpenAI tool calling format)
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_documents",
        "description": "Sucht in den Unterlagen des Restaurants (Speisekarte mit Allergenen, Öffnungszeiten, Reservierung, "
                       "Catering, Hygiene/HACCP, Einkauf). Für jede Frage zu Gerichten, Regeln oder Abläufen verwenden.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_stock",
        "description": "Aktueller Bestand einer Zutat aus der Warenwirtschaft.",
        "parameters": {"type": "object", "properties": {"ingredient": {"type": "string"}}, "required": ["ingredient"]}}},
    {"type": "function", "function": {
        "name": "low_stock",
        "description": "Alle Zutaten unter Mindestbestand.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "propose_purchase_order",
        "description": "Bestellvorschlag je Lieferant für alle Zutaten unter Mindestbestand (wird nicht gesendet).",
        "parameters": {"type": "object", "properties": {"supplier": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "check_availability",
        "description": "Prüft, ob eine Reservierung möglich ist (Öffnungszeiten, Gruppengröße, freie Plätze).",
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string", "description": "Datum im Format YYYY-MM-DD"},
            "at": {"type": "string", "description": "Uhrzeit im Format HH:MM"},
            "persons": {"type": "integer"}}, "required": ["day", "at", "persons"]}}},
    {"type": "function", "function": {
        "name": "list_reservations",
        "description": "Reservierungen für einen Tag (YYYY-MM-DD) oder alle kommenden.",
        "parameters": {"type": "object", "properties": {"day": {"type": "string"}}}}},
]
