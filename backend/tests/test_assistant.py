"""The assistant answers only from documents and systems, and says so when it finds nothing."""
import json
from types import SimpleNamespace

from app.assistant import NOT_FOUND, Assistant
from app.tools import Tools


def test_stock_answer_comes_from_the_stock_system(db):
    r = Assistant(Tools(db)).ask("Haben wir noch Kokosmilch?")
    assert "Kokosmilch: 8" in r.answer and "unter Mindestbestand" in r.answer
    assert r.receipt[0]["label"] == "Warenwirtschaft › Kokosmilch"


def test_document_answer_names_its_source(db):
    r = Assistant(Tools(db)).ask("Welche Temperatur muss der Kühlschrank haben?")
    assert "2 bis 7 °C" in r.answer
    assert "Quelle: Hygiene und HACCP › Kühlung" in r.answer


def test_unknown_question_is_refused_not_invented(db):
    r = Assistant(Tools(db)).ask("Wie wird das Wetter am Wochenende?")
    assert r.answer == NOT_FOUND


def test_allergen_answer_is_read_from_the_menu(db):
    r = Assistant(Tools(db)).ask("Welche Gerichte gehen bei Erdnussallergie?")
    safe, unsafe = r.answer.split("\n")[:2]
    assert "Rendang Sapi" in safe and "Gado-Gado" not in safe
    assert "Gado-Gado" in unsafe and "Sate Ayam" in unsafe


def test_monday_is_closed(db):
    r = Assistant(Tools(db)).ask("Haben wir Montag um 19 Uhr einen Tisch für 2 frei?")
    assert r.answer.startswith("Leider nicht.") and "Ruhetag" in r.answer


class FakeLLM:
    """Stands in for an OpenAI-compatible server: first asks for a tool, then answers with what the tool returned."""

    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        tool_msgs = [m for m in kw["messages"] if m["role"] == "tool"]
        if not tool_msgs:
            call = SimpleNamespace(id="c1", function=SimpleNamespace(name="get_stock", arguments=json.dumps({"ingredient": "Tempeh"})))
            msg = SimpleNamespace(content=None, tool_calls=[call])
        else:
            stock = json.loads(tool_msgs[-1]["content"])["ingredients"][0]["stock"]
            msg = SimpleNamespace(content=f"Wir haben noch {stock:g} Packungen Tempeh.", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_model_mode_runs_tools_and_reports_them(db, monkeypatch):
    from app import assistant as mod
    monkeypatch.setattr(mod.settings.__class__, "llm_provider", "openai", raising=False)
    llm = FakeLLM()
    r = Assistant(Tools(db), client=llm).ask("Wie viel Tempeh ist da?")
    assert r.answer == "Wir haben noch 3 Packungen Tempeh."
    assert r.receipt == [{"kind": "system", "label": "Warenwirtschaft › Tempeh", "detail": "Bestand 3 Packung (250 g)"}]
    assert llm.calls[0]["tools"], "the model is offered the tools"


def test_model_cannot_call_unknown_tools(db):
    a = Assistant(Tools(db), client=FakeLLM())
    assert a._run_tool("book_stock", '{"ingredient_id": "reis", "change": -30, "reason": "x"}') == {"error": "unbekanntes Werkzeug"}
