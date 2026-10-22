"""Turns incoming guest e-mails into checked drafts. The model (or, in demo mode, a parser) only extracts what the guest
wants; whether a table is free, what catering costs and whether the lead time is met is computed in code.
A person reviews every draft before anything is sent or booked.
"""
import json
import re
from datetime import date, timedelta

from . import dates
from .assistant import Assistant, fmt_eur
from .config import settings
from .tools import Tools

CATERING_PRICE = {"klassik": 24.0, "vegetarisch": 21.0}

EXTRACT_PROMPT = """Lies die E-Mail an ein Restaurant und gib NUR JSON zurück:
{"kind": "reservierung" | "catering" | "frage" | "sonstiges", "name": str|null, "day": "YYYY-MM-DD"|null,
 "time": "HH:MM"|null, "persons": int|null, "vegetarian": bool, "allergies": [str], "question": str|null}
Heute ist {today}. Rechne Wochentage wie "Samstag" in das nächste passende Datum um. Erfinde nichts, was nicht in der E-Mail steht."""

REPLY_PROMPT = """Schreibe eine kurze, freundliche Antwort-E-Mail im Namen des Restaurants Rumah Makan Nusantara (Sie-Form,
geschlechtsneutrale Anrede mit vollem Namen, z. B. "Hallo Kim Schäfer,"). Verwende NUR diese geprüften Fakten und erfinde
keine Zusagen, Preise oder Gerichte:
{facts}
Unterschreibe mit "Ihr Team vom Rumah Makan Nusantara"."""


class Inbox:
    def __init__(self, tools: Tools, assistant: Assistant):
        self.tools = tools
        self.assistant = assistant

    def messages(self) -> list[dict]:
        rows = self.tools.db.query("SELECT * FROM inbox ORDER BY received_at DESC")
        for r in rows:
            r["result"] = json.loads(r["result"]) if r["result"] else None
        return rows

    def get(self, mail_id: int) -> dict:
        rows = [r for r in self.messages() if r["id"] == mail_id]
        if not rows:
            raise KeyError(mail_id)
        return rows[0]

    # --- step 1: understand -----------------------------------------------------------------------------------
    def extract(self, mail: dict) -> dict:
        if self.assistant.client is not None:
            r = self.assistant.client.chat.completions.create(
                model=settings.llm_model, temperature=0, max_tokens=300, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": EXTRACT_PROMPT.replace("{today}", dates.today().isoformat())},
                          {"role": "user", "content": f"Von: {mail['sender']}\nBetreff: {mail['subject']}\n\n{mail['body'][:3000]}"}])
            data = json.loads(r.choices[0].message.content)
            data.setdefault("name", mail["sender"])
            return data
        return parse_mail(mail)

    # --- step 2: check against the systems and write a draft ----------------------------------------------------
    def process(self, mail_id: int, actor: str = "Personal") -> dict:
        mail = self.get(mail_id)
        info = self.extract(mail)
        facts, receipt, action = [], [], None
        kind = info.get("kind")
        if kind == "reservierung" and info.get("day") and info.get("time") and info.get("persons"):
            check = self.tools.check_availability(info["day"], info["time"], int(info["persons"]))
            receipt.append({"kind": "system", "label": f"Reservierungsbuch › {check['day_label']}", "detail": check["reason"]})
            if check["possible"]:
                facts.append(f"Reservierung ist möglich: {check['day_label']}, {info['time']} Uhr, {info['persons']} Personen. "
                             "Der Tisch wird 15 Minuten freigehalten.")
                action = {"type": "reservation", "name": info.get("name") or mail["sender"], "day": info["day"],
                          "time": info["time"], "persons": int(info["persons"]),
                          "notes": ", ".join(f"Allergie: {a}" for a in info.get("allergies") or [])}
            else:
                facts.append(f"Die gewünschte Reservierung ({check['day_label']}, {info['time']} Uhr) ist nicht möglich: {check['reason']}")
                alt = self.alternative(info["day"], info["time"], int(info["persons"]))
                if alt:
                    facts.append(f"Alternativvorschlag: {alt['day_label']} um {alt['time']} Uhr ist frei.")
                    receipt.append({"kind": "system", "label": f"Reservierungsbuch › {alt['day_label']}", "detail": "Alternative frei"})
        elif kind == "catering" and info.get("persons"):
            persons = int(info["persons"])
            variant = "vegetarisch" if info.get("vegetarian") else "klassik"
            price = CATERING_PRICE[variant] * persons
            day = date.fromisoformat(info["day"]) if info.get("day") else None
            lead = 10 if persons > 50 else 5
            facts.append(f"Buffet {'Vegetarisch' if variant == 'vegetarisch' else 'Klassik'}: {fmt_eur(CATERING_PRICE[variant])} pro Person, "
                         f"für {persons} Personen also {fmt_eur(price)}. Lieferung im Umkreis von 20 km ist ab 300 € kostenlos. "
                         "Geschirr-Leihe 2 € pro Person. Die Bestellung ist nach Bestätigung eines schriftlichen Angebots verbindlich.")
            if day:
                ok = (day - dates.today()).days >= lead
                facts.append(f"Termin {dates.fmt_date(day)}: " + ("der nötige Vorlauf ist eingehalten." if ok else
                             f"zu kurzfristig, wir brauchen mindestens {lead} Tage Vorlauf."))
            if persons < 15:
                facts.append("Catering bieten wir erst ab 15 Personen an.")
            receipt.append({"kind": "doc", "label": "Catering › Preise", "detail": f"{variant}: {fmt_eur(CATERING_PRICE[variant])} p. P."})
            receipt.append({"kind": "doc", "label": "Catering › Vorlauf und Bestellung", "detail": f"mindestens {lead} Tage"})
            action = {"type": "catering_offer", "total": price, "persons": persons, "variant": variant}
        if info.get("allergies") or kind == "frage" or (kind == "reservierung" and "allerg" in mail["body"].lower()):
            question = info.get("question") or mail["body"]
            reply = self.assistant._ask_demo(question, audience="guest")  # rule-based lookup: facts straight from the documents
            facts.append(reply.answer)
            receipt += reply.receipt
        if not facts:
            facts.append("Die Anfrage konnte nicht automatisch zugeordnet werden; bitte persönlich beantworten.")
        draft = self.write_reply(mail, info, facts)
        result = {"kind": kind, "extracted": info, "facts": facts, "draft": draft, "action": action, "receipt": receipt,
                  "mode": self.assistant.mode}
        self.tools.db.execute("UPDATE inbox SET status = 'Entwurf', result = ? WHERE id = ?",
                              (json.dumps(result, ensure_ascii=False), mail_id))
        self.tools.db.audit(actor, "E-Mail ausgewertet", {"mail": mail_id, "art": kind, "modus": self.assistant.mode})
        return self.get(mail_id)

    def alternative(self, day: str, at: str, persons: int) -> dict | None:
        d = date.fromisoformat(day)
        for offset in range(0, 8):
            for t in ([at] if offset else []) + ["18:00", "19:00", "20:00", "12:30"]:
                check = self.tools.check_availability((d + timedelta(days=offset)).isoformat(), t, persons)
                if check["possible"]:
                    return check
        return None

    def write_reply(self, mail: dict, info: dict, facts: list[str]) -> str:
        name = info.get("name") or mail["sender"]
        if self.assistant.client is not None:
            r = self.assistant.client.chat.completions.create(
                model=settings.llm_model, temperature=0.3, max_tokens=450,
                messages=[{"role": "system", "content": REPLY_PROMPT.replace("{facts}", "\n".join(f"- {f}" for f in facts))},
                          {"role": "user", "content": f"E-Mail von {name}:\n{mail['body'][:2000]}"}])
            return r.choices[0].message.content.strip()
        body = "\n\n".join(re.sub(r"\n\nQuellen?: .*$", "", f, flags=re.S) for f in facts)
        return f"Hallo {name},\n\nvielen Dank für Ihre Nachricht.\n\n{body}\n\nViele Grüße\nIhr Team vom Rumah Makan Nusantara"

    # --- step 3: a person approves --------------------------------------------------------------------------------
    def approve(self, mail_id: int, draft: str | None = None, actor: str = "Personal") -> dict:
        mail = self.get(mail_id)
        result = mail["result"]
        if not result:
            raise ValueError("Die E-Mail wurde noch nicht ausgewertet.")
        if draft:
            result["draft"] = draft
        action = result.get("action")
        if action and action["type"] == "reservation":
            res = self.tools.add_reservation(action["name"], action["day"], action["time"], action["persons"],
                                             action["notes"], "E-Mail", actor)
            result["booked"] = res
        self.tools.db.execute("UPDATE inbox SET status = 'Beantwortet (Demo, keine echte E-Mail)', result = ? WHERE id = ?",
                              (json.dumps(result, ensure_ascii=False), mail_id))
        self.tools.db.audit(actor, "Antwort freigegeben", {"mail": mail_id, "an": mail["address"], "aktion": action["type"] if action else None})
        return self.get(mail_id)


def parse_mail(mail: dict) -> dict:
    """Demo extraction without a language model: keywords and the German date parser."""
    text = f"{mail['subject']}\n{mail['body']}"
    t = text.lower()
    day = dates.parse_date(t)
    at = dates.parse_time(t)
    if "catering" in t or "buffet" in t:
        kind = "catering"
    elif re.search(r"reservier|tisch", t):
        kind = "reservierung"
    elif "?" in text:
        kind = "frage"
    else:
        kind = "sonstiges"
    allergies = [w for w in ("erdnuss", "gluten", "laktose", "soja", "sesam") if w in t]
    question = None
    if kind == "frage":
        question = " ".join(s for s in re.split(r"(?<=[?.!])\s+", mail["body"]) if s.strip().endswith("?"))
    elif allergies:
        question = f"Welche Gerichte gehen bei {allergies[0]}allergie?"
    return {"kind": kind, "name": mail["sender"], "day": day.isoformat() if day else None,
            "time": at.strftime("%H:%M") if at else None, "persons": dates.parse_persons(t),
            "vegetarian": "vegetarisch" in t or "vegan" in t, "allergies": allergies, "question": question}
