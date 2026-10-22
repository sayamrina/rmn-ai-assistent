"""Retrieval over the restaurant's own documents (Markdown, split at ## headings) with BM25.

Every passage keeps its document and section title, so each answer can name its source.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

DOCS = Path(__file__).parent / "knowledge"
MIN_SCORE = 1.5  # below this, nothing in the documents answers the question

STOP = set("""der die das den dem des ein eine einer eines einem einen und oder aber mit ohne für von zu zum zur im in am an auf
aus bei ist sind war wird werden hat haben habt gibt es ich du wir ihr sie er man kann können könnt wie was wann wo welche
welcher welches noch auch nicht kein keine bitte gern gerne mal uns euch euer eure unser unsere dass ob so sehr""".split())


@dataclass
class Passage:
    doc: str
    title: str
    section: str
    text: str

    @property
    def source(self) -> str:
        return f"{self.title} › {self.section}"


def normalise(word: str) -> str:
    w = word.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    for suffix in ("ungen", "ung", "en", "er", "es", "e", "n", "s"):
        if len(w) > 5 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


# everyday words staff use for terms that appear differently in the documents
SYNONYMS = {
    "offen": "öffnungszeiten geöffnet", "geöffnet": "öffnungszeiten", "auf": "öffnungszeiten",
    "kosten": "preis preise", "kostet": "preis preise", "teuer": "preis", "haltbar": "verbraucht mindesthaltbarkeitsdatum",
    "allergie": "allergene", "allergiker": "allergene", "erdnussallergie": "erdnüsse allergene",
    "glutenfrei": "gluten", "laktosefrei": "milch", "kühlschrank": "kühlung", "temperatur": "kühlung",
    "tisch": "reservierung", "reservieren": "reservierung", "bestellen": "bestellung", "nachbestellen": "bestellung",
}


def tokens(text: str, expand: bool = False) -> list[str]:
    words = [w for w in re.findall(r"[\wäöüß-]+", text.lower()) if w not in STOP and len(w) > 1 and not w.isdigit()]
    if expand:
        words += [x for w in words for x in SYNONYMS.get(w, "").split()]
    return [normalise(w) for w in words]


class Knowledge:
    def __init__(self, folder: Path = DOCS):
        self.passages: list[Passage] = []
        for path in sorted(folder.glob("*.md")):
            title, section, lines = path.stem, "", []
            for line in path.read_text(encoding="utf-8").splitlines() + ["## "]:
                if line.startswith("# "):
                    title, section = line[2:].strip(), "Allgemein"
                elif line.startswith("## "):
                    if section and lines:
                        self.passages.append(Passage(path.stem, title, section, " ".join(lines).strip()))
                    section, lines = line[3:].strip(), []
                elif line.strip():
                    lines.append(line.strip())
        # section titles count twice: "Rendang Sapi" should find the Rendang passage first
        self.bm25 = BM25Okapi([tokens(f"{p.title} {p.section} {p.section} {p.text}") for p in self.passages])

    def search(self, query: str, k: int = 3) -> list[tuple[Passage, float]]:
        q = tokens(query, expand=True)
        if not q:
            return []
        scores = self.bm25.get_scores(q)
        ranked = sorted(zip(self.passages, scores), key=lambda x: -x[1])
        return [(p, float(s)) for p, s in ranked[:k] if s >= MIN_SCORE]


knowledge = Knowledge()
