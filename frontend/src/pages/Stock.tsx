import { useEffect, useState } from "react";
import { api, fmtEur, fmtQty, type Ingredient, type Proposal, type PurchaseOrder } from "../api";

const REASONS = ["Wareneingang", "Verbrauch", "Verderb", "Inventur"];

export default function Stock() {
  const [items, setItems] = useState<Ingredient[]>([]);
  const [proposal, setProposal] = useState<Proposal[]>([]);
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [error, setError] = useState("");
  const [booking, setBooking] = useState({ id: "kokosmilch", change: "12", reason: "Wareneingang" });
  const [approved, setApproved] = useState<Record<number, boolean>>({});

  async function load() {
    try {
      const [s, p, o] = await Promise.all([api.stock(), api.proposal(), api.orders()]);
      setItems(s);
      setProposal(p.orders);
      setOrders(o);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => { void load(); }, []);

  async function act(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const low = items.filter((i) => i.below_min).length;

  return (
    <>
      <header className="page-head">
        <h1>Vorrat & Einkauf</h1>
        <span className="id" lang="id">Gudang &amp; belanja</span>
        <p>Bestände aus der Warenwirtschaft. Liegt eine Zutat unter dem Mindestbestand, entsteht ein Bestellvorschlag; übermittelt wird erst nach deiner Bestätigung.</p>
      </header>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="grid-2">
        <section className="panel">
          <h2>Bestand</h2>
          <p className="muted" style={{ margin: 0 }}>{low} von {items.length} Zutaten unter Mindestbestand. Der Strich markiert den Mindestbestand.</p>
          <table>
            <thead>
              <tr><th>Zutat</th><th className="num">Bestand</th><th className="hide-sm">Lieferant</th></tr>
            </thead>
            <tbody>
              {items.map((i) => {
                const max = Math.max(i.stock, i.min_stock * 2);
                return (
                  <tr key={i.id} className={i.below_min ? "low" : ""}>
                    <td>
                      {i.name} {i.below_min && <span className="tag warn">nachbestellen</span>}
                      <div className="meter" aria-hidden="true">
                        <i className={i.below_min ? "low" : ""} style={{ width: `${(i.stock / max) * 100}%` }} />
                        <b style={{ left: `${(i.min_stock / max) * 100}%` }} />
                      </div>
                    </td>
                    <td className="num">{fmtQty(i.stock)}<div className="muted" style={{ fontSize: 13 }}>{i.unit}</div></td>
                    <td className="hide-sm muted">{i.supplier}<div style={{ fontSize: 13 }}>{i.storage}</div></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <form className="form-row" onSubmit={(e) => {
            e.preventDefault();
            const n = Number(booking.change.replace(",", "."));
            const sign = booking.reason === "Wareneingang" || booking.reason === "Inventur" ? 1 : -1;
            void act(() => api.book(booking.id, sign * Math.abs(n), booking.reason));
          }}>
            <label>Zutat
              <select value={booking.id} onChange={(e) => setBooking({ ...booking, id: e.target.value })}>
                {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </label>
            <label>Menge
              <input inputMode="decimal" size={5} value={booking.change} onChange={(e) => setBooking({ ...booking, change: e.target.value })} />
            </label>
            <label>Grund
              <select value={booking.reason} onChange={(e) => setBooking({ ...booking, reason: e.target.value })}>
                {REASONS.map((r) => <option key={r}>{r}</option>)}
              </select>
            </label>
            <button className="btn">Buchen</button>
          </form>
        </section>

        <div style={{ display: "grid", gap: 20 }}>
          <section className="panel">
            <h2>Bestellvorschlag</h2>
            <p className="muted" style={{ margin: 0 }}>Bis zum Zielbestand (doppelter Mindestbestand), in vollen Gebinden.</p>
            {proposal.length === 0 && <p>Gerade muss nichts nachbestellt werden.</p>}
            {proposal.map((p) => (
              <div className="po" key={p.supplier_id}>
                <b>{p.supplier}</b> <span className="muted">· {fmtEur(p.total)}</span>
                <ul>
                  {p.lines.map((l) => <li key={l.ingredient}>{fmtQty(l.quantity)} × {l.ingredient} <span className="muted">({l.unit})</span></li>)}
                </ul>
                <div className="muted" style={{ fontSize: 13 }}>{p.delivery}</div>
                {p.below_min_order && <p className="tag gold">Unter dem Mindestbestellwert von {fmtEur(p.min_order)}</p>}
                {p.needs_approval && <p className="tag gold">Über 500 €: Freigabe der Restaurantleitung nötig</p>}
                <div><button className="btn small" onClick={() => act(() => api.createOrder(p.supplier_id))}>Bestellentwurf anlegen</button></div>
              </div>
            ))}
          </section>

          <section className="panel">
            <h2>Bestellungen</h2>
            {orders.length === 0 && <p className="muted">Noch keine Bestellentwürfe.</p>}
            {orders.map((o) => (
              <div className="po" key={o.id}>
                <b>#{o.id} {o.supplier}</b> <span className="muted">· {fmtEur(o.total)}</span>
                <div><span className={o.status.startsWith("An Lieferant") ? "tag" : "tag gold"}>{o.status}</span></div>
                {!o.status.startsWith("An Lieferant") && (
                  <div className="form-row">
                    {o.needs_approval && (
                      <label style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                        <input type="checkbox" checked={!!approved[o.id]} onChange={(e) => setApproved({ ...approved, [o.id]: e.target.checked })} />
                        Restaurantleitung hat freigegeben
                      </label>
                    )}
                    <button className="btn small solid" onClick={() => act(() => api.sendOrder(o.id, !!approved[o.id]))}>
                      An {o.email} übermitteln
                    </button>
                  </div>
                )}
              </div>
            ))}
          </section>
        </div>
      </div>
    </>
  );
}
