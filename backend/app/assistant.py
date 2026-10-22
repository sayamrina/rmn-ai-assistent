"""The chat assistant. With a language model it plans tool calls itself; in demo mode a small rule-based router calls
the same tools. Either way every answer carries a receipt ("Nota") of what was looked up, and nothing is invented:
without a matching document or system entry, the assistant says so.
"""
import json
import re
from dataclasses import dataclass, field

from . import dates
from .config import settings
from .tools import TOOL_SCHEMAS, Tools

NOT_FOUND = ("Dazu finde ich nichts in unseren Unterlagen oder Systemen. Bitte frag die Restaurantleitung, "
             "statt zu raten.")

SYSTEM = f"""Du bist der interne KI-Assistent des Restaurants Rumah Makan Nusantara in Saarbrücken und hilfst dem Personal.
Antworte kurz, freundlich und auf Deutsch (Du-Form unter Kollegen).
Regeln:
- Beantworte Fragen zu Gerichten, Allergenen, Öffnungszeiten, Reservierung, Catering, Hygiene und Einkauf NUR mit Informationen
  aus search_documents. Nenne am Ende die Quelle(n) in der Form "Quelle: <Quelle>".
- Bestände, Bestellvorschläge und freie Plätze holst du immer über die Werkzeuge, nie aus dem Gedächtnis.
- Wenn die Werkzeuge nichts liefern, sag ehrlich: "{NOT_FOUND}"
- Bei Allergien: nur sagen, was in der Speisekarte steht, und auf die Küchenleitung verweisen, wenn etwas unklar ist.
- Du sendest nichts und bestellst nichts selbst; Bestellungen und Antworten bestätigt immer ein Mensch.
Heute ist {{today}}."""


@dataclass
class Reply:
    answer: str
    receipt: list[dict] = field(default_factory=list)  # [{"kind": "doc"|"system", "label": ..., "detail": ...}]
    mode: str = "demo"


class Assistant:
    def __init__(self, tools: Tools, client=None):
        self.tools = tools
        self.client = client  # OpenAI-compatible client, or None for demo mode

    @property
    def mode(self) -> str:
        return "demo" if self.client is None else settings.llm_provider

    def ask(self, question: str, history: list[dict] | None = None) -> Reply:
        question = question.strip()[:800]
        reply = self._ask_demo(question) if self.client is None else self._ask_llm(question, history or [])
        self.tools.db.audit("Assistent", "Frage beantwortet", {"frage": question, "modus": reply.mode,
                                                               "nachgeschlagen": [r["label"] for r in reply.receipt]})
        return reply

    # --- demo: rules decide which tool to call ----------------------------------------------------------------
    def _ask_demo(self, q: str, audience: str = "staff") -> Reply:
        t = q.lower()
        dish = next((p for p in self.tools.menu_passages() if p.section.split(" (")[0].lower() in t), None)
        if dish:
            return self._answer_dish(dish)
        if re.search(r"nachbestell|bestellvorschlag|einkaufsliste|was (müssen|sollen) wir bestellen", t):
            return self._answer_order_proposal()
        if re.search(r"knapp|mindestbestand|unter (dem )?minimum|was fehlt|ausgeh", t):
            return self._answer_low_stock()
        if re.search(r"vorrat|bestand|lager|haben wir noch|noch da|wie viel|wieviel", t):
            found = self.tools.get_stock(q)
            if found["found"]:
                return self._answer_stock(found["ingredients"])
        allergen = next((code for word, code in ALLERGEN_WORDS.items() if word in t), None)
        if allergen and re.search(r"allerg|unverträglich|ohne|frei\b|vertr", t):
            return self._answer_allergen(allergen, audience)
        if re.search(r"tisch|reservier|platz|plätze|frei", t) and dates.parse_date(t):
            return self._answer_availability(t)
        return self._answer_documents(q)

    def _answer_documents(self, q: str) -> Reply:
        hits = self.tools.search_documents(q)["passages"]
        if not hits:
            return Reply(NOT_FOUND, [{"kind": "doc", "label": "Unterlagen durchsucht", "detail": "kein passender Abschnitt"}])
        best = hits[0]
        sentences = re.split(r"(?<=[.!?])\s+", best["text"])
        words = {w for w in re.findall(r"\w{4,}", q.lower())}
        relevant = [s for s in sentences if words & set(re.findall(r"\w{4,}", s.lower()))] or sentences[:2]
        answer = " ".join(relevant[:3]) + f"\n\nQuelle: {best['source']}"
        receipt = [{"kind": "doc", "label": h["source"], "detail": h["text"][:160] + ("…" if len(h["text"]) > 160 else "")}
                   for h in hits[:2]]
        return Reply(answer, receipt)

    def _answer_dish(self, dish) -> Reply:
        return Reply(f"{dish.section}: {dish.text}\n\nQuelle: {dish.source}",
                     [{"kind": "doc", "label": dish.source, "detail": dish.text[:160]}])

    def _answer_allergen(self, code: str, audience: str = "staff") -> Reply:
        """Read the allergen codes straight from the menu, so the answer is exactly what the menu says."""
        safe, unsafe = [], []
        for p in self.tools.menu_passages():
            m = re.search(r"Allergene: ([^.]*)", p.text)
            if not m:
                continue
            (unsafe if re.search(rf"\b{code}\b", m.group(1)) else safe).append(p.section)
        name = ALLERGEN_NAMES[code]
        if audience == "guest":
            answer = (f"Ohne {name} sind laut unserer Speisekarte: {', '.join(safe)}. {name} enthalten: {', '.join(unsafe) or 'keine Gerichte'}. "
                      "Bitte weisen Sie unser Service-Team beim Besuch noch einmal auf die Allergie hin, dann bereitet die Küche "
                      "Arbeitsfläche und Utensilien gesondert vor. Spuren können wir leider nicht ganz ausschließen.")
        else:
            answer = (f"Laut Speisekarte ohne {name} ({code}): {', '.join(safe)}.\n"
                      f"Enthalten {name}: {', '.join(unsafe) or 'keine'}.\n"
                      "Spuren können wir in unserer Küche nicht ausschließen. Bei einer Allergie bitte die Küchenleitung informieren, "
                      "damit Arbeitsfläche und Utensilien vorher gereinigt werden.\n\n"
                      "Quellen: Speisekarte (Allergenangaben), Hygiene und HACCP › Allergene")
        return Reply(answer, [{"kind": "doc", "label": "Speisekarte › Allergenangaben aller Gerichte", "detail": f"Allergen {code}: {name}"},
                              {"kind": "doc", "label": "Hygiene und HACCP › Allergene", "detail": "Utensilien und Arbeitsfläche vorher reinigen"}])

    def _answer_stock(self, items: list[dict]) -> Reply:
        lines = []
        for i in items:
            flag = " (unter Mindestbestand!)" if i["below_min"] else ""
            lines.append(f"{i['name']}: {fmt_qty(i['stock'])} × {i['unit']}{flag}, Mindestbestand {fmt_qty(i['min_stock'])}.")
        receipt = [{"kind": "system", "label": f"Warenwirtschaft › {i['name']}",
                    "detail": f"Bestand {fmt_qty(i['stock'])} {i['unit']} · Lager: {i['storage']} · Lieferant: {i['supplier']}"}
                   for i in items]
        return Reply("\n".join(lines), receipt)

    def _answer_low_stock(self) -> Reply:
        low = self.tools.low_stock()["ingredients"]
        if not low:
            return Reply("Alle Zutaten liegen über dem Mindestbestand.", [{"kind": "system", "label": "Warenwirtschaft › Mindestbestände", "detail": "keine Unterschreitung"}])
        lines = [f"- {i['name']}: {fmt_qty(i['stock'])} von mindestens {fmt_qty(i['min_stock'])} ({i['unit']}), Lieferant {i['supplier']}" for i in low]
        return Reply(f"{len(low)} Zutaten liegen unter dem Mindestbestand:\n" + "\n".join(lines) +
                     "\n\nUnter „Vorrat“ kannst du daraus einen Bestellentwurf machen.",
                     [{"kind": "system", "label": "Warenwirtschaft › Mindestbestände", "detail": f"{len(low)} Unterschreitungen"}])

    def _answer_order_proposal(self) -> Reply:
        orders = self.tools.propose_purchase_order()["orders"]
        if not orders:
            return Reply("Es muss gerade nichts nachbestellt werden.", [{"kind": "system", "label": "Einkauf › Bestellvorschlag", "detail": "leer"}])
        parts = []
        for o in orders:
            items = ", ".join(f"{fmt_qty(line['quantity'])} × {line['ingredient']}" for line in o["lines"])
            note = " Braucht Freigabe der Restaurantleitung (über 500 €)." if o["needs_approval"] else ""
            if o["below_min_order"]:
                note += f" Achtung: unter dem Mindestbestellwert von {fmt_eur(o['min_order'])}."
            parts.append(f"{o['supplier']}: {items}. Summe {fmt_eur(o['total'])}.{note}")
        return Reply("Bestellvorschlag bis zum Zielbestand (doppelter Mindestbestand):\n" + "\n".join(f"- {p}" for p in parts) +
                     "\n\nDie Bestellung wird erst nach deiner Bestätigung unter „Vorrat“ übermittelt.\n\nQuelle: Einkauf und Lieferanten › Bestellmenge",
                     [{"kind": "system", "label": "Einkauf › Bestellvorschlag", "detail": f"{len(orders)} Lieferanten"},
                      {"kind": "doc", "label": "Einkauf und Lieferanten › Bestellmenge", "detail": "Zielbestand = doppelter Mindestbestand"}])

    def _answer_availability(self, t: str) -> Reply:
        day = dates.parse_date(t)
        at = dates.parse_time(t)
        persons = dates.parse_persons(t) or 2
        if at is None:
            rows = self.tools.list_reservations(day.isoformat())
            listing = "\n".join(f"- {r['time']} Uhr: {r['name']}, {r['persons']} Personen" for r in rows) or "- noch keine"
            return Reply(f"Reservierungen am {dates.fmt_date(day)}:\n{listing}\n\nNenn mir eine Uhrzeit, dann prüfe ich die freien Plätze.",
                         [{"kind": "system", "label": f"Reservierungsbuch › {dates.fmt_date(day)}", "detail": f"{len(rows)} Reservierungen"}])
        check = self.tools.check_availability(day.isoformat(), at.strftime("%H:%M"), persons)
        verdict = "Ja, das geht." if check["possible"] else "Leider nicht."
        return Reply(f"{verdict} {dates.fmt_date(day)}, {at.strftime('%H:%M')} Uhr, {persons} Personen: {check['reason']}",
                     [{"kind": "system", "label": f"Reservierungsbuch › {dates.fmt_date(day)}", "detail": check["reason"]}])

    # --- language model: it chooses the tools ------------------------------------------------------------------
    def _ask_llm(self, q: str, history: list[dict]) -> Reply:
        messages = [{"role": "system", "content": SYSTEM.replace("{today}", dates.fmt_date(dates.today()))}]
        messages += [{"role": m["role"], "content": m["content"][:800]} for m in history[-6:] if m.get("role") in ("user", "assistant")]
        messages.append({"role": "user", "content": q})
        receipt: list[dict] = []
        for _ in range(4):
            r = self.client.chat.completions.create(model=settings.llm_model, messages=messages, tools=TOOL_SCHEMAS,
                                                    temperature=0.1, max_tokens=500)
            msg = r.choices[0].message
            if not msg.tool_calls:
                return Reply((msg.content or NOT_FOUND).strip(), receipt, self.mode)
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in msg.tool_calls]})
            for call in msg.tool_calls:
                result = self._run_tool(call.function.name, call.function.arguments)
                receipt += receipt_for(call.function.name, result)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)[:6000]})
        return Reply(NOT_FOUND, receipt, self.mode)

    def _run_tool(self, name: str, arguments: str) -> dict:
        allowed = {s["function"]["name"] for s in TOOL_SCHEMAS}
        if name not in allowed:
            return {"error": "unbekanntes Werkzeug"}
        try:
            args = json.loads(arguments or "{}")
            result = getattr(self.tools, name)(**args)
            return result if isinstance(result, dict) else {"items": result}
        except Exception as e:  # the model sees the error and can correct its call
            return {"error": str(e)}


def receipt_for(name: str, result: dict) -> list[dict]:
    if "error" in result:
        return [{"kind": "system", "label": name, "detail": f"Fehler: {result['error']}"}]
    if name == "search_documents":
        return [{"kind": "doc", "label": p["source"], "detail": p["text"][:160]} for p in result["passages"][:2]] or \
               [{"kind": "doc", "label": "Unterlagen durchsucht", "detail": "kein passender Abschnitt"}]
    if name == "get_stock":
        return [{"kind": "system", "label": f"Warenwirtschaft › {i['name']}", "detail": f"Bestand {fmt_qty(i['stock'])} {i['unit']}"}
                for i in result["ingredients"]] or [{"kind": "system", "label": "Warenwirtschaft", "detail": "Zutat nicht gefunden"}]
    if name == "low_stock":
        return [{"kind": "system", "label": "Warenwirtschaft › Mindestbestände", "detail": f"{result['count']} Unterschreitungen"}]
    if name == "propose_purchase_order":
        return [{"kind": "system", "label": "Einkauf › Bestellvorschlag", "detail": f"{len(result['orders'])} Lieferanten"}]
    if name == "check_availability":
        return [{"kind": "system", "label": f"Reservierungsbuch › {result.get('day_label', '')}", "detail": result.get("reason", "")}]
    if name == "list_reservations":
        return [{"kind": "system", "label": "Reservierungsbuch", "detail": f"{len(result.get('items', []))} Reservierungen"}]
    return [{"kind": "system", "label": name, "detail": ""}]


ALLERGEN_WORDS = {"erdnuss": "E", "erdnüss": "E", "gluten": "A", "weizen": "A", "eier": "C", "ei-": "C", "soja": "F",
                  "milch": "G", "laktose": "G", "sesam": "L", "sellerie": "I", "krebs": "B", "garnele": "B", "fisch": "D", "senf": "K"}
ALLERGEN_NAMES = {"A": "Gluten", "B": "Krebstiere", "C": "Eier", "D": "Fisch", "E": "Erdnüsse", "F": "Soja", "G": "Milch",
                  "H": "Schalenfrüchte", "I": "Sellerie", "K": "Senf", "L": "Sesam"}


def fmt_eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_qty(x: float) -> str:
    return f"{x:g}".replace(".", ",")
