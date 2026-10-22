import { useEffect, useState } from "react";
import { api, type Meta } from "./api";
import Chat from "./pages/Chat";
import Stock from "./pages/Stock";
import Inbox from "./pages/Inbox";
import Reservations from "./pages/Reservations";
import Audit from "./pages/Audit";
import About from "./pages/About";

const PAGES = [
  { id: "assistent", label: "Assistent", component: Chat },
  { id: "vorrat", label: "Vorrat & Einkauf", component: Stock },
  { id: "posteingang", label: "Posteingang", component: Inbox },
  { id: "reservierungen", label: "Reservierungen", component: Reservations },
  { id: "protokoll", label: "Protokoll", component: Audit },
  { id: "info", label: "Über & Anleitung", component: About },
] as const;

type PageId = (typeof PAGES)[number]["id"];

function currentPage(): PageId {
  const hash = window.location.hash.replace("#/", "");
  return (PAGES.find((p) => p.id === hash)?.id ?? "assistent") as PageId;
}

export default function App() {
  const [page, setPage] = useState<PageId>(currentPage);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [newMail, setNewMail] = useState(0);

  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener("hashchange", onHash);
    api.meta().then(setMeta).catch(() => setMeta(null));
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    api.inbox().then((m) => setNewMail(m.filter((x) => x.status === "neu").length)).catch(() => undefined);
  }, [page]);

  const go = (id: PageId) => {
    window.location.hash = `#/${id}`;
  };
  const Current = PAGES.find((p) => p.id === page)!.component;

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <b>RMN AI Assistent</b>
          <span>Rumah Makan Nusantara · Saarbrücken</span>
        </div>
        <nav className="nav" aria-label="Bereiche">
          {PAGES.map((p) => (
            <button key={p.id} aria-current={p.id === page ? "page" : undefined} onClick={() => go(p.id)}>
              {p.label}
              {p.id === "posteingang" && newMail > 0 && <span className="count" aria-label={`${newMail} neue E-Mails`}>{newMail}</span>}
            </button>
          ))}
        </nav>
        <div className="mode">
          {meta?.mode === "demo" ? (
            <>
              <b>Demo-Modus.</b> Antworten kommen regelbasiert aus Unterlagen und Systemen, ohne Sprachmodell.
            </>
          ) : meta ? (
            <>
              <b>Sprachmodell:</b> {meta.model}
            </>
          ) : null}
          <br />
          Fiktives Restaurant, alle Daten sind Beispieldaten.
        </div>
      </aside>
      <main>
        <aside className="project-popup" aria-label="Portfolio project">
          <span className="project-popup-badge" aria-hidden="true">★</span>
          <span>This app was developed by Amrina as part of a portfolio.</span>
          <a href="https://sayamrina.github.io/" target="_blank" rel="noopener">View the portfolio →</a>
        </aside>
        <Current />
      </main>
    </div>
  );
}
