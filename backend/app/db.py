"""SQLite store for the restaurant's stock management, reservations, inbox and audit log, with sample data.

The schema stands in for the restaurant's existing systems (Warenwirtschaft, reservation book, mailbox).
The assistant only reaches them through the functions in tools.py, the same way it would call a real API.
"""
import json
import sqlite3
import threading
from datetime import date, datetime, timedelta

from . import dates
from .config import settings

SCHEMA = """
CREATE TABLE suppliers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, delivery TEXT NOT NULL, min_order REAL NOT NULL
);
CREATE TABLE ingredients (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, aliases TEXT NOT NULL, unit TEXT NOT NULL,
  stock REAL NOT NULL CHECK (stock >= 0), min_stock REAL NOT NULL, pack_size REAL NOT NULL,
  price REAL NOT NULL, supplier_id TEXT NOT NULL REFERENCES suppliers(id), storage TEXT NOT NULL
);
CREATE TABLE purchase_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id TEXT NOT NULL REFERENCES suppliers(id), status TEXT NOT NULL,
  lines TEXT NOT NULL, total REAL NOT NULL, needs_approval INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, day TEXT NOT NULL, time TEXT NOT NULL,
  persons INTEGER NOT NULL CHECK (persons > 0), notes TEXT NOT NULL DEFAULT '', source TEXT NOT NULL
);
CREATE TABLE inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, address TEXT NOT NULL, subject TEXT NOT NULL,
  body TEXT NOT NULL, received_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'neu', result TEXT
);
CREATE TABLE audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL
);
"""

SUPPLIERS = [
    ("asia", "Asia-Großhandel", "bestellung@asia-grosshandel.example", "Bestellschluss 12:00 Uhr, Lieferung am nächsten Werktag", 150),
    ("frische", "Frischedienst", "auftrag@frischedienst.example", "Lieferung Dienstag und Freitag, Bestellschluss am Vortag 16:00 Uhr", 0),
    ("halal", "Halal-Metzgerei", "bestellung@halal-metzgerei.example", "Lieferung Dienstag und Samstag, Bestellung zwei Tage vorher", 0),
]

# id, name, aliases, unit, stock, min_stock, pack_size, price per unit, supplier, storage
INGREDIENTS = [
    ("kokosmilch", "Kokosmilch", "santan,kokos,coconut", "Dose (400 ml)", 8, 24, 12, 1.35, "asia", "Trockenlager"),
    ("kecap", "Kecap Manis", "sojasauce,süße sojasauce", "Flasche", 9, 6, 6, 3.20, "asia", "Trockenlager"),
    ("tempeh", "Tempeh", "", "Packung (250 g)", 3, 10, 10, 2.10, "asia", "Kühlung"),
    ("tofu", "Tofu", "", "Packung (400 g)", 14, 8, 8, 1.90, "asia", "Kühlung"),
    ("reis", "Jasminreis", "reis,beras", "kg", 32, 20, 10, 2.40, "asia", "Trockenlager"),
    ("erdnuesse", "Erdnüsse", "kacang,erdnuss", "kg", 2.5, 3, 1, 6.80, "asia", "Trockenlager"),
    ("krupuk", "Krupuk Udang", "krupuk,kerupuk,cracker", "Packung", 11, 6, 6, 2.60, "asia", "Trockenlager"),
    ("glasnudeln", "Glasnudeln", "soun,bihun,nudeln", "Packung", 7, 5, 10, 1.50, "asia", "Trockenlager"),
    ("kurkuma", "Kurkuma (frisch)", "kunyit,kurkuma", "kg", 0.8, 0.5, 0.5, 9.50, "asia", "Kühlung"),
    ("limetten", "Limetten", "jeruk nipis,limette", "Stück", 12, 40, 20, 0.25, "frische", "Kühlung"),
    ("eier", "Eier", "telur,ei", "Stück", 60, 60, 30, 0.28, "frische", "Kühlung"),
    ("kangkung", "Wasserspinat (Kangkung)", "kangkung,wasserspinat", "Bund", 5, 8, 4, 2.20, "frische", "Kühlung"),
    ("chili", "Rote Chili (frisch)", "cabai,cabe,chili", "kg", 1.2, 1, 0.5, 8.40, "frische", "Kühlung"),
    ("rind", "Rindfleisch (halal)", "rind,daging sapi,rendang", "kg", 4, 6, 1, 18.90, "halal", "Kühlung"),
    ("haehnchen", "Hähnchenschenkel (halal)", "hähnchen,huhn,ayam", "kg", 9, 8, 2, 7.90, "halal", "Kühlung"),
]

INBOX = [
    ("Jona Weber", "jona.weber@post.example", "Tischreservierung Samstag",
     "Hallo liebes Nusantara-Team,\n\nwir möchten gern am Samstag um 19 Uhr einen Tisch für 6 Personen reservieren. "
     "Eine Person in unserer Gruppe hat eine Erdnussallergie. Welche Gerichte könnt ihr da empfehlen?\n\nViele Grüße\nJona Weber"),
    ("Kim Schäfer", "k.schaefer@buero-saar.example", "Catering für unsere Teamfeier",
     "Guten Tag,\n\nfür unsere Teamfeier am {catering_day} suchen wir ein Catering für 30 Personen, gern vegetarisch. "
     "Lieferung nach Saarbrücken-Mitte. Was würde das ungefähr kosten?\n\nBeste Grüße\nKim Schäfer"),
    ("Alex Brandt", "alex.brandt@mail.example", "Frage zu Gado-Gado",
     "Hallo,\n\nist euer Gado-Gado vegan und ist es glutenfrei? Ich ernähre mich vegan.\n\nDanke!\nAlex"),
    ("Robin Hahn", "robin.hahn@post.example", "Reservierung Montag",
     "Guten Tag,\n\nhaben Sie am Montag um 12:30 Uhr einen Tisch für 4 Personen frei?\n\nMit freundlichen Grüßen\nRobin Hahn"),
]


class Database:
    def __init__(self, path: str = settings.db_path, ref_day: date | None = None):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.ref_day = ref_day or dates.today()
        self.seed()

    def seed(self):
        with self.lock:
            c = self.conn
            c.executescript(SCHEMA)
            c.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?)", SUPPLIERS)
            c.executemany("INSERT INTO ingredients VALUES (?,?,?,?,?,?,?,?,?,?)", INGREDIENTS)
            # a few existing reservations in the coming days
            sat = self.ref_day + timedelta(days=(5 - self.ref_day.weekday()) % 7 or 7)
            rows = [("Familie Lorenz", sat, "19:00", 8, "Geburtstag"), ("Sam Keller", sat, "19:30", 4, ""),
                    ("Firma Tegtmeier", sat, "18:30", 12, "Reistafel"),
                    ("Noa Fischer", self.ref_day + timedelta(days=1), "12:30", 2, "")]
            c.executemany("INSERT INTO reservations (name, day, time, persons, notes, source) VALUES (?,?,?,?,?, 'Telefon')",
                          [(n, d.isoformat(), t, p, x) for n, d, t, p, x in rows])
            catering_day = dates.fmt_date(self.ref_day + timedelta(days=9))
            now = datetime.now().replace(microsecond=0)
            c.executemany("INSERT INTO inbox (sender, address, subject, body, received_at) VALUES (?,?,?,?,?)",
                          [(s, a, sub, b.replace("{catering_day}", catering_day), (now - timedelta(minutes=37 * i)).isoformat())
                           for i, (s, a, sub, b) in enumerate(INBOX)])
            c.commit()

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    def audit(self, actor: str, action: str, detail: dict | str):
        text = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
        self.execute("INSERT INTO audit (at, actor, action, detail) VALUES (?,?,?,?)",
                     (datetime.now().replace(microsecond=0).isoformat(), actor, action, text[:2000]))
