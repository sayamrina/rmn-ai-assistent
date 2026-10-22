import { useEffect, useState } from "react";
import { api, fmtDay, type Reservation } from "../api";

export default function Reservations() {
  const [rows, setRows] = useState<Reservation[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api.reservations().then(setRows).catch((e) => setError((e as Error).message)); }, []);

  const days = [...new Set(rows.map((r) => r.day))];

  return (
    <>
      <header className="page-head">
        <h1>Reservierungen</h1>
        <p>Das Reservierungsbuch der nächsten Tage. 40 Plätze, davon 10 für Gäste ohne Reservierung; ein Tisch ist etwa zwei Stunden belegt.</p>
      </header>
      {error && <p className="error" role="alert">{error}</p>}
      {days.length === 0 && <p className="muted">Keine kommenden Reservierungen.</p>}
      <div style={{ display: "grid", gap: 16 }}>
        {days.map((d) => {
          const list = rows.filter((r) => r.day === d);
          return (
            <section className="panel" key={d}>
              <h2>{fmtDay(d)}</h2>
              <p className="muted" style={{ margin: 0 }}>{list.reduce((s, r) => s + r.persons, 0)} Personen in {list.length} Reservierungen</p>
              <table>
                <thead><tr><th>Uhrzeit</th><th>Name</th><th className="num">Personen</th><th>Hinweis</th><th className="hide-sm">Quelle</th></tr></thead>
                <tbody>
                  {list.map((r) => (
                    <tr key={r.id}>
                      <td>{r.time}</td><td>{r.name}</td><td className="num">{r.persons}</td>
                      <td>{r.notes && <span className={/allerg/i.test(r.notes) ? "tag warn" : "tag"}>{r.notes}</span>}</td>
                      <td className="hide-sm muted">{r.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          );
        })}
      </div>
    </>
  );
}
