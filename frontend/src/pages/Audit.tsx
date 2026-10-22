import { useEffect, useState } from "react";
import { api, type AuditEntry } from "../api";

function detail(text: string): string {
  try {
    const d = JSON.parse(text) as Record<string, unknown>;
    return Object.entries(d)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
      .join(" · ");
  } catch {
    return text;
  }
}

export default function Audit() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  useEffect(() => { api.audit().then(setRows).catch(() => setRows([])); }, []);
  return (
    <>
      <header className="page-head">
        <h1>Protokoll</h1>
        <span className="id" lang="id">Catatan kegiatan</span>
        <p>Jede Antwort des Assistenten und jede Buchung, Bestellung und Freigabe wird mit Zeitpunkt festgehalten. So lässt sich später nachvollziehen, wer was ausgelöst hat.</p>
      </header>
      {rows.length === 0 && <p className="muted">Noch keine Einträge. Stell im Assistenten eine Frage oder buche einen Bestand.</p>}
      {rows.length > 0 && (
        <section className="panel">
          <table>
            <thead><tr><th>Zeit</th><th>Wer</th><th>Was</th><th className="hide-sm">Details</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="num" style={{ textAlign: "left" }}>{r.at.replace("T", " ").slice(5, 16)}</td>
                  <td>{r.actor}</td>
                  <td>{r.action}</td>
                  <td className="hide-sm muted" style={{ fontSize: 13.5 }}>{detail(r.detail)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
