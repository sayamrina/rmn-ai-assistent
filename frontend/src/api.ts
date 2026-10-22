export type ReceiptLine = { kind: "doc" | "system"; label: string; detail: string };
export type ChatReply = { answer: string; receipt: ReceiptLine[]; mode: string };
export type Ingredient = {
  id: string; name: string; stock: number; unit: string; min_stock: number;
  below_min: boolean; supplier: string; storage: string;
};
export type OrderLine = { ingredient: string; quantity: number; unit: string; price: number; total: number };
export type Proposal = {
  supplier_id: string; supplier: string; delivery: string; min_order: number;
  lines: OrderLine[]; total: number; needs_approval: boolean; below_min_order: boolean;
};
export type PurchaseOrder = {
  id: number; supplier: string; email: string; status: string; lines: OrderLine[];
  total: number; needs_approval: boolean; created_at: string;
};
export type Reservation = { id: number; name: string; day: string; time: string; persons: number; notes: string; source: string };
export type MailResult = {
  kind: string | null;
  extracted: Record<string, unknown>;
  facts: string[];
  draft: string;
  action: Record<string, unknown> | null;
  receipt: ReceiptLine[];
  mode: string;
  booked?: Reservation;
};
export type Mail = {
  id: number; sender: string; address: string; subject: string; body: string;
  received_at: string; status: string; result: MailResult | null;
};
export type AuditEntry = { id: number; at: string; actor: string; action: string; detail: string };
export type Meta = { mode: string; model: string | null; restaurant: string; seats: number };

function sessionId(): string {
  try {
    let id = localStorage.getItem("rmn-session");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("rmn-session", id);
    }
    return id;
  } catch {
    return "anonym";
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Session-Id": sessionId(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let message = `Fehler ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch { /* keep the status message */ }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown = {}) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  meta: () => call<Meta>("/api/meta"),
  chat: (question: string, history: { role: string; content: string }[]) => post<ChatReply>("/api/chat", { question, history }),
  stock: () => call<Ingredient[]>("/api/stock"),
  book: (id: string, change: number, reason: string) => post<{ stock: number }>(`/api/stock/${id}/bookings`, { change, reason }),
  proposal: () => call<{ orders: Proposal[] }>("/api/purchase-orders/proposal"),
  orders: () => call<PurchaseOrder[]>("/api/purchase-orders"),
  createOrder: (supplier_id: string) => post<PurchaseOrder>("/api/purchase-orders", { supplier_id }),
  sendOrder: (id: number, approved: boolean) => post<PurchaseOrder>(`/api/purchase-orders/${id}/send`, { approved }),
  reservations: () => call<Reservation[]>("/api/reservations"),
  inbox: () => call<Mail[]>("/api/inbox"),
  process: (id: number) => post<Mail>(`/api/inbox/${id}/process`),
  approve: (id: number, draft: string) => post<Mail>(`/api/inbox/${id}/approve`, { draft }),
  audit: () => call<AuditEntry[]>("/api/audit"),
};

export const fmtQty = (x: number) => x.toLocaleString("de-DE", { maximumFractionDigits: 2 });
export const fmtEur = (x: number) => x.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
export const fmtDay = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString("de-DE", { weekday: "long", day: "2-digit", month: "2-digit" });
