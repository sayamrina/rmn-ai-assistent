export default function About() {
  return (
    <>
      <header className="page-head">
        <h1>Über & Anleitung</h1>
        <p>Ein KI-Assistent für das Personal eines Restaurants: Fragen beantworten, Vorrat im Blick behalten, Anfragen von Gästen vorbereiten.</p>
      </header>
      <div className="prose">
        <p>
          Das <b>Rumah Makan Nusantara</b> in Saarbrücken ist ein <b>fiktives</b> indonesisches Restaurant. Speisekarte, Bestände,
          Reservierungen und E-Mails sind Beispieldaten. Die App zeigt, wie ein kleiner Betrieb KI im Alltag nutzen kann,
          ohne dass die KI etwas erfindet oder allein entscheidet.
        </p>

        <h2>So probierst du es aus</h2>
        <ol className="steps">
          <li><b>Assistent:</b> Klick auf eine Beispielfrage, etwa „Welche Gerichte gehen bei Erdnussallergie?“. Unter der Antwort steht, wo der Assistent nachgeschaut hat.</li>
          <li>Frag etwas, das nicht in den Unterlagen steht, zum Beispiel nach dem Wetter. Der Assistent sagt dann ehrlich, dass er es nicht weiß.</li>
          <li><b>Vorrat & Einkauf:</b> Sechs Zutaten liegen unter dem Mindestbestand. Lege für einen Lieferanten einen Bestellentwurf an und übermittle ihn.</li>
          <li><b>Posteingang:</b> Öffne die Reservierungsanfrage für Samstag und klick auf „Auswerten“. Der Assistent prüft die freien Plätze und die Allergene und schreibt einen Entwurf.</li>
          <li>Gib die Antwort frei. Die Reservierung erscheint unter <b>Reservierungen</b>, der Vorgang im <b>Protokoll</b>.</li>
          <li>Probier auch die Anfrage für Montag (Ruhetag) und die Catering-Anfrage aus.</li>
        </ol>

        <h2>Was dahintersteckt</h2>
        <ul>
          <li><b>Wissensdatenbank mit RAG:</b> Speisekarte, Allergene, Öffnungszeiten, Catering, Hygiene und Einkauf werden durchsucht; jede Antwort nennt ihre Quelle. Ohne passende Stelle antwortet der Assistent nicht.</li>
          <li><b>Werkzeuge über eine REST-API:</b> Bestand, Bestellvorschlag, freie Plätze und Reservierungen kommen aus den Systemen des Restaurants. Regeln wie Mindestbestand, Bestellmengen, Öffnungszeiten und Kapazität rechnet der Code, nicht das Sprachmodell.</li>
          <li><b>Mensch entscheidet:</b> Bestellungen über 500 € brauchen eine Freigabe, Antworten an Gäste werden geprüft, alles landet im Protokoll.</li>
          <li><b>Modell nach Wahl:</b> Die App spricht die OpenAI-kompatible Schnittstelle und läuft mit OpenAI oder mit einem eigenen Modell im eigenen Rechenzentrum (z. B. Ollama oder vLLM). Im Demo-Modus antwortet sie regelbasiert ganz ohne Sprachmodell.</li>
        </ul>

        <h2>Technik</h2>
        <p>Python und FastAPI im Backend, SQLite, BM25-Suche, Tool Calling; React mit TypeScript im Frontend; automatisierte Tests, Docker und Continuous Integration.</p>
        <p>
          <a href="https://sayamrina.github.io/rmn-ai-assistent/">Projektseite</a> ·{" "}
          <a href="https://github.com/sayamrina/rmn-ai-assistent">Quellcode</a> ·{" "}
          <a href="https://sayamrina.github.io/" target="_blank" rel="noopener">Portfolio von Amrina</a>
        </p>
        <p className="muted">Diese App wurde von Amrina entwickelt, mit KI als unterstützendem Werkzeug beim Programmieren.</p>
      </div>
    </>
  );
}
