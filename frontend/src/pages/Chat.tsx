import { useEffect, useRef, useState } from "react";
import { api, type ReceiptLine } from "../api";

type Message = { role: "user" | "assistant"; content: string; receipt?: ReceiptLine[] };

const SUGGESTIONS = [
  "Was müssen wir nachbestellen?",
  "Haben wir noch Kokosmilch?",
  "Welche Gerichte gehen bei Erdnussallergie?",
  "Ist Gado-Gado vegan?",
  "Haben wir Samstag um 19 Uhr Platz für 6 Personen?",
  "Welche Temperatur muss der Kühlschrank haben?",
];

const WELCOME: Message = {
  role: "assistant",
  content:
    "Selamat datang! Ich beantworte Fragen zu Speisekarte, Allergenen, Reservierungen, Catering, Hygiene und Einkauf. " +
    "Ich schaue dafür in unseren Unterlagen und Systemen nach und zeige dir unter jeder Antwort, wo.",
};

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setError("");
    setInput("");
    const history = messages.filter((m) => m !== WELCOME).map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: q }]);
    setBusy(true);
    try {
      const r = await api.chat(q, history);
      setMessages((m) => [...m, { role: "assistant", content: r.answer, receipt: r.receipt }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page-head">
        <h1>Assistent</h1>
        <span className="id" lang="id">Asisten</span>
        <p>Frag wie eine Kollegin oder einen Kollegen. Der Assistent antwortet nur aus Unterlagen und Systemen und sagt ehrlich, wenn er etwas nicht weiß.</p>
      </header>
      <section className="chat">
        <div className="thread" aria-live="polite">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="msg user">{m.content}</div>
            ) : (
              <div key={i} className="msg bot">
                <div className="bubble">{m.content}</div>
                {m.receipt && m.receipt.length > 0 && <Nota lines={m.receipt} />}
              </div>
            ),
          )}
          {busy && <div className="typing">Sebentar, schaut nach …</div>}
          {messages.length === 1 && (
            <div className="suggest" aria-label="Beispielfragen">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => ask(s)}>{s}</button>
              ))}
            </div>
          )}
          <div ref={end} />
        </div>
        <div>
          {error && <p className="error" role="alert">{error}</p>}
          <form className="ask" onSubmit={(e) => { e.preventDefault(); void ask(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="z. B. Wie lange ist offene Kokosmilch haltbar?"
              aria-label="Frage an den Assistenten" maxLength={800} />
            <button className="btn solid" disabled={busy || !input.trim()}>Fragen</button>
          </form>
        </div>
      </section>
    </>
  );
}

export function Nota({ lines }: { lines: ReceiptLine[] }) {
  return (
    <div className="nota" aria-label="Nachgeschlagen">
      <div className="title">Nachgeschlagen</div>
      {lines.map((l, i) => (
        <div className="line" key={i}>
          <span className="k">{l.kind === "doc" ? "Dokument" : "System"}</span>
          <span>
            {l.label}
            {l.detail && <span className="muted"> · {l.detail}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
