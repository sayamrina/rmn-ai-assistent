"""REST API of the RMN AI Assistent. The React frontend is served from the same origin."""
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .assistant import Assistant
from .config import settings
from .db import Database
from .inbox import Inbox
from .tools import Tools

STATIC = Path(__file__).resolve().parent.parent / "static"


def make_client():
    if settings.llm_provider == "demo":
        return None
    from openai import OpenAI
    if settings.llm_provider == "openai":
        return OpenAI(api_key=settings.openai_api_key, timeout=30)
    return OpenAI(base_url=settings.llm_base_url, api_key="local", timeout=60)  # Ollama, vLLM, LM Studio …


class Limiter:
    """Bounds model calls on a public demo: per browser session per hour, and per day overall."""

    def __init__(self):
        self.sessions: dict[str, deque] = defaultdict(deque)
        self.day: tuple[str, int] = ("", 0)

    def check(self, session: str):
        now = time.time()
        q = self.sessions[session]
        while q and now - q[0] > 3600:
            q.popleft()
        today = time.strftime("%Y-%m-%d")
        if self.day[0] != today:
            self.day = (today, 0)
        if len(q) >= settings.session_limit_per_hour or self.day[1] >= settings.global_limit_per_day:
            raise HTTPException(429, "Das Kontingent für Modellanfragen ist erreicht. Bitte später noch einmal versuchen.")
        q.append(now)
        self.day = (today, self.day[1] + 1)


def create_app(db: Database | None = None, client=None) -> FastAPI:
    app = FastAPI(title="RMN AI Assistent", version="1.0.0",
                  description="KI-Assistent für das Personal des Rumah Makan Nusantara (fiktives Restaurant)")
    app.state.db = db or Database()
    tools = Tools(app.state.db)
    assistant = Assistant(tools, client if client is not None else make_client())
    inbox = Inbox(tools, assistant)
    limiter = Limiter()

    def session(request: Request) -> str:
        return request.headers.get("x-session-id") or (request.client.host if request.client else "anon")

    def guard(request: Request):
        if assistant.client is not None:
            limiter.check(session(request))

    class Question(BaseModel):
        question: str = Field(min_length=1, max_length=800)
        history: list[dict] = Field(default_factory=list, max_length=12)

    class Booking(BaseModel):
        change: float
        reason: str = Field(min_length=1, max_length=200)

    class Approval(BaseModel):
        draft: str | None = Field(default=None, max_length=5000)

    class NewOrder(BaseModel):
        supplier_id: str = Field(min_length=1, max_length=40)

    class Send(BaseModel):
        approved: bool = False

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta():
        return {"mode": assistant.mode, "model": None if assistant.client is None else settings.llm_model,
                "restaurant": "Rumah Makan Nusantara, Saarbrücken (fiktiv)", "seats": settings.seats}

    @app.post("/api/chat")
    def chat(q: Question, request: Request):
        guard(request)
        r = assistant.ask(q.question, q.history)
        return {"answer": r.answer, "receipt": r.receipt, "mode": r.mode}

    @app.get("/api/stock")
    def stock():
        return tools.list_stock()

    @app.post("/api/stock/{ingredient_id}/bookings")
    def book(ingredient_id: str, b: Booking):
        try:
            return tools.book_stock(ingredient_id, b.change, b.reason)
        except KeyError:
            raise HTTPException(404, "Zutat nicht gefunden")
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/purchase-orders/proposal")
    def proposal():
        return tools.propose_purchase_order()

    @app.get("/api/purchase-orders")
    def purchase_orders():
        return tools.list_purchase_orders()

    @app.post("/api/purchase-orders", status_code=201)
    def create_po(body: NewOrder):
        try:
            return tools.create_purchase_order(body.supplier_id)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/purchase-orders/{po_id}/send")
    def send_po(po_id: int, body: Send | None = None):
        try:
            return tools.send_purchase_order(po_id, approved=bool(body and body.approved))
        except KeyError:
            raise HTTPException(404, "Bestellung nicht gefunden")
        except PermissionError as e:
            raise HTTPException(403, str(e))

    @app.get("/api/reservations")
    def reservations(day: str | None = None):
        return tools.list_reservations(day)

    @app.get("/api/inbox")
    def mails():
        return inbox.messages()

    @app.post("/api/inbox/{mail_id}/process")
    def process(mail_id: int, request: Request):
        guard(request)
        try:
            return inbox.process(mail_id)
        except KeyError:
            raise HTTPException(404, "E-Mail nicht gefunden")

    @app.post("/api/inbox/{mail_id}/approve")
    def approve(mail_id: int, a: Approval):
        try:
            return inbox.approve(mail_id, a.draft)
        except KeyError:
            raise HTTPException(404, "E-Mail nicht gefunden")
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/audit")
    def audit():
        return app.state.db.query("SELECT * FROM audit ORDER BY id DESC LIMIT 200")

    if STATIC.exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Nicht gefunden")
            file = (STATIC / path).resolve()
            if path and file.is_file() and STATIC in file.parents:
                return FileResponse(file)
            return FileResponse(STATIC / "index.html")

    return app


app = create_app()
