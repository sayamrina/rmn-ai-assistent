import { useEffect, useState } from "react";
import { api, fmtDay, type Mail } from "../api";
import { Nota } from "./Chat";

const KIND: Record<string, string> = { reservierung: "Reservierung", catering: "Catering", frage: "Frage", sonstiges: "Sonstiges" };
const FIELDS: [string, string][] = [["name", "Name"], ["day", "Datum"], ["time", "Uhrzeit"], ["persons", "Personen"], ["allergies", "Allergien"]];

export default function Inbox() {
  const [mails, setMails] = useState<Mail[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load(keep?: number) {
    const m = await api.inbox();
    setMails(m);
    const id = keep ?? selected ?? m[0]?.id ?? null;
    setSelected(id);
    setDraft(m.find((x) => x.id === id)?.result?.draft ?? "");
  }
  useEffect(() => { load().catch((e) => setError((e as Error).message)); }, []);

  const mail = mails.find((m) => m.id === selected);
  const r = mail?.result;
  const done = mail?.status.startsWith("Beantwortet");

  async function run(fn: () => Promise<Mail>) {
    setBusy(true);
    setError("");
    try {
      const m = await fn();
      await load(m.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page-head">
        <h1>Posteingang</h1>
        <p>Der Assistent liest Anfragen von Gästen, prüft sie gegen Reservierungsbuch, Speisekarte und Preisliste und schreibt einen Antwortentwurf. Gesendet und gebucht wird erst, wenn du freigibst.</p>
      </header>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="inbox">
        <div className="mails" role="list">
          {mails.map((m) => (
            <button key={m.id} role="listitem" aria-pressed={m.id === selected}
              onClick={() => { setSelected(m.id); setDraft(m.result?.draft ?? ""); }}>
              <div className="from">{m.sender}</div>
              <div className="subj">{m.subject}</div>
              <span className={m.status === "neu" ? "tag gold" : "tag"}>{m.status === "neu" ? "neu" : m.status.startsWith("Beantwortet") ? "beantwortet" : "Entwurf"}</span>
            </button>
          ))}
        </div>

        {mail && (
          <section className="panel">
            <h2>{mail.subject}</h2>
            <div className="muted">{mail.sender} &lt;{mail.address}&gt;</div>
            <div className="mail-body">{mail.body}</div>

            {!r && (
              <p style={{ marginTop: 14 }}>
                <button className="btn solid" disabled={busy} onClick={() => run(() => api.process(mail.id))}>
                  {busy ? "Prüft …" : "Auswerten und Antwort entwerfen"}
                </button>
              </p>
            )}

            {r && (
              <>
                <h3 style={{ marginBottom: 0 }}>Erkannt: {KIND[r.kind ?? "sonstiges"] ?? r.kind}</h3>
                <dl className="extract">
                  {FIELDS.filter(([k]) => r.extracted[k] && String(r.extracted[k]) !== "").map(([k, label]) => (
                    <div key={k} style={{ display: "contents" }}>
                      <dt>{label}</dt>
                      <dd>{k === "day" ? fmtDay(String(r.extracted[k])) : Array.isArray(r.extracted[k]) ? (r.extracted[k] as string[]).join(", ") : String(r.extracted[k])}</dd>
                    </div>
                  ))}
                </dl>
                {r.receipt.length > 0 && <Nota lines={r.receipt} />}
                <h3>Antwortentwurf</h3>
                <textarea className="draft" value={draft} onChange={(e) => setDraft(e.target.value)} disabled={done} aria-label="Antwortentwurf" />
                {r.action?.type === "reservation" && !done && (
                  <p className="muted">Beim Freigeben wird die Reservierung ins Reservierungsbuch eingetragen.</p>
                )}
                {done ? (
                  <p><span className="tag">{mail.status}</span>{r.booked && <> Reservierung #{r.booked.id} eingetragen.</>}</p>
                ) : (
                  <p>
                    <button className="btn solid" disabled={busy} onClick={() => run(() => api.approve(mail.id, draft))}>
                      Antwort freigeben
                    </button>{" "}
                    <button className="btn" disabled={busy} onClick={() => run(() => api.process(mail.id))}>Neu auswerten</button>
                  </p>
                )}
              </>
            )}
          </section>
        )}
      </div>
    </>
  );
}
