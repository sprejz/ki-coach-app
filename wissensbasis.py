"""
Wissensbasis (RAG) — Transkripte/Texte in Chunks, Embeddings, Vektorsuche.
Chromadb mit fastembed (lokal, mehrsprachig, Open Source).
Embedder und Store injizierbar für Tests.
"""

import json
import uuid
from pathlib import Path
from typing import Optional


class WissensbasisStore:
    """
    Chroma-basierte Wissensbasis mit fastembed-Embeddings.
    Lazy-Laden des Modells (beim ersten Gebrauch, nicht beim Import).
    """

    def __init__(
        self,
        data_dir: Path,
        embedder_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
        embedder_class=None,
        chroma_client=None,
    ):
        """
        embedder_class: optionale Test-Attrappe (TextEmbedding-ähnliche API).
        chroma_client: optionaler Test-Client (PersistentClient-ähnlich).
        """
        self.data_dir = Path(data_dir)
        self.embedder_model = embedder_model
        self._embedder = None
        self._embedder_class = embedder_class
        self._chroma_client = chroma_client
        self._collection = None

    def _ensure_embedder(self):
        """Lazy-Laden des Embedders (fastembed oder Test-Attrappe)."""
        if self._embedder is None:
            if self._embedder_class:
                self._embedder = self._embedder_class(model_name=self.embedder_model)
            else:
                from fastembed import TextEmbedding

                self._embedder = TextEmbedding(model_name=self.embedder_model)

    def _get_collection(self):
        """Lazy-Laden der Chroma-Collection."""
        if self._collection is None:
            if self._chroma_client:
                client = self._chroma_client
            else:
                import chromadb

                client = chromadb.PersistentClient(
                    path=str(self.data_dir / "chroma")
                )
            self._collection = client.get_or_create_collection(
                name="wissen",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @staticmethod
    def chunk_segments(
        text: str,
        start_s: int = 0,
        chunk_size_tokens: int = 256,
        overlap_ratio: float = 0.2,
    ) -> list[tuple[int, int, str]]:
        """
        Text in Chunks mit Overlap, Zeitstempel behalten.

        Arg:
            text: Transkript (z.B. von youtube.py oder Freitext)
            start_s: Startzeit des Texts in Sekunden (für Video-Segmente)
            chunk_size_tokens: Ziel-Chunkgröße in Tokens (~4 Zeichen/Token, grob)
            overlap_ratio: Überlappung (0.2 = 20%)

        Return:
            [(start_s, end_s, chunk_text), ...] — jeder Chunk hat eine Startzeit (Estimate).

        Strategie: Split bei Absätzen/Sätzen statt rohe Tokens (kein Tokenizer nötig).
        """
        if not text.strip():
            return []

        # Charakter-basierte Estimate: ~4 Zeichen/Token
        chunk_size_chars = chunk_size_tokens * 4
        overlap_chars = int(chunk_size_chars * overlap_ratio)

        chunks = []
        pos = 0
        while pos < len(text):
            chunk_end = min(pos + chunk_size_chars, len(text))

            # Über Satzende splitten, wenn möglich
            if chunk_end < len(text):
                last_period = text.rfind(".", pos, chunk_end)
                if last_period > pos + chunk_size_chars * 0.5:  # nicht zu nah am Start
                    chunk_end = last_period + 1

            chunk_text = text[pos : chunk_end].strip()
            if chunk_text:
                # Geschätzter Prozentsatz der Videozeit
                chunk_pos_ratio = pos / len(text) if len(text) > 0 else 0
                chunk_start_s = int(start_s + chunk_pos_ratio * 3600)  # Max ~1h estimate
                chunk_end_s = int(start_s + (chunk_end / len(text)) * 3600)

                chunks.append((chunk_start_s, chunk_end_s, chunk_text))

            pos = chunk_end - overlap_chars

        return chunks

    def add_source(
        self,
        source_id: str,
        title: str,
        text: str,
        source_url: str,
        start_s: int = 0,
    ) -> dict:
        """
        Quelle hinzufügen: Text chunken, embedden, speichern.

        Return: {id, titel, quelle, chunks_count, erstellt_am}
        """
        self._ensure_embedder()
        collection = self._get_collection()

        chunks = self.chunk_segments(text, start_s=start_s)
        if not chunks:
            raise ValueError("Keine Chunks aus dem Text")

        # Embeddings berechnen
        chunk_texts = [chunk[2] for chunk in chunks]
        embeddings = list(
            self._embedder.embed(chunk_texts)
        )  # fastembed gibt Generator zurück

        # Speichern in Chroma
        ids = [f"{source_id}_{i:04d}" for i in range(len(chunks))]
        metadatas = [
            {
                "source_id": source_id,
                "titel": title,
                "quelle": source_url,
                "start_s": chunk[0],
                "end_s": chunk[1],
            }
            for chunk in chunks
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunk_texts,
        )

        # Metadaten (Quelle selbst) speichern
        source_meta = {
            "id": source_id,
            "titel": title,
            "quelle": source_url,
            "chunks": len(chunks),
            "erstellt_am": json.dumps(
                __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
            ).strip('"'),
        }

        return source_meta

    def search(
        self, query_text: str, n_results: int = 5, min_confidence: float = 0.3
    ) -> list[dict]:
        """
        Frage stellen: Frage embedden, Ähnlichkeitssuche, Treffer mit Quelle zurück.

        Return: [{text, title, source_url, start_s, relevance}, ...]
        """
        if not query_text.strip():
            return []

        self._ensure_embedder()
        collection = self._get_collection()

        # Query embedden
        query_embedding = list(self._embedder.embed([query_text]))[0]

        # Suchen
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results * 2,  # Überabfragen, dann filtern
            include=["documents", "metadatas", "distances"],
        )

        # distances → similarities (Cosine: 0=ähnlich, 2=unähnlich; hier Cosine distance)
        # Umrechnung: similarity ≈ 1 - distance/2
        treffer = []
        for i in range(len(results["documents"][0])):
            distance = results["distances"][0][i]
            similarity = max(0, 1 - distance / 2)  # Normalisierung auf [0, 1]

            if similarity >= min_confidence:
                meta = results["metadatas"][0][i]
                treffer.append(
                    {
                        "text": results["documents"][0][i],
                        "titel": meta.get("titel", "?"),
                        "quelle": meta.get("quelle", "?"),
                        "start_s": meta.get("start_s", 0),
                        "relevance": round(similarity, 2),
                    }
                )

        return treffer[:n_results]

    def list_sources(self) -> list[dict]:
        """Alle Quellen auflisten (eindeutige source_ids mit Metadaten)."""
        collection = self._get_collection()

        # Chroma: get() ohne where() gibt alles zurück
        all_data = collection.get(include=["metadatas"])

        # source_id nach Erstem Vorkommen gruppieren
        sources_by_id = {}
        for meta in all_data["metadatas"]:
            source_id = meta.get("source_id")
            if source_id and source_id not in sources_by_id:
                sources_by_id[source_id] = {
                    "id": source_id,
                    "titel": meta.get("titel", "?"),
                    "quelle": meta.get("quelle", "?"),
                }

        # Chunks pro Quelle zählen
        for meta in all_data["metadatas"]:
            source_id = meta.get("source_id")
            if source_id in sources_by_id:
                sources_by_id[source_id].setdefault("chunks", 0)
                sources_by_id[source_id]["chunks"] += 1

        return list(sources_by_id.values())

    def delete_source(self, source_id: str) -> bool:
        """Quelle und alle ihre Chunks löschen. Return True wenn gelöscht, False wenn nicht found."""
        collection = self._get_collection()

        # Chroma löscht via where-Filter
        try:
            collection.delete(where={"source_id": source_id})
            return True
        except Exception:
            return False

    def get_collection_stats(self) -> dict:
        """Diagnostik: Anzahl Chunks, Quellen."""
        collection = self._get_collection()
        all_data = collection.get()
        unique_sources = len(set(m.get("source_id") for m in all_data.get("metadatas", [])))
        return {
            "chunks": len(all_data.get("documents", [])),
            "sources": unique_sources,
        }
