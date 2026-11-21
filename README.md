# Lab 3 (PJN) — wyszukiwanie pełnotekstowe: PostgreSQL kontra Solr

Porównanie LIKE, indeksu pełnotekstowego PostgreSQL (tsvector + GIN) i Apache Solr 10 na metadanych arXiv
(źródło: Cornell University, licencja CC0; mirror Hugging Face `librarian-bots/arxiv-metadata-snapshot`).
Poziom realizacji: 5.0. Dokument jest wersją startową — kolejne sekcje powstaną w następnych etapach.

## Wymagania
- Docker Desktop (Windows/macOS) lub Docker Engine (Linux) z `docker compose`; **min. 6 GB RAM** przydzielone Dockerowi.
- Python 3.11+.
- Wolne porty: 5432 (Postgres, można zmienić `PG_PORT`) i 8983 (Solr).

## Uruchomienie

1. Konfiguracja:
   ```
   cp .env.example .env        # Windows: copy .env.example .env
   ```
   Jeśli port 5432 jest zajęty (np. przez lokalnego Postgresa), ustaw w `.env` inny `PG_PORT`, np. `5433`.

2. Kontenery:
   ```
   docker compose up -d
   docker compose ps          # poczekaj na status "healthy" obu usług
   ```

3. Środowisko Pythona:
   ```
   python -m venv venv
   source venv/bin/activate         # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. Sprawdzenie środowiska:
   ```
   python -m lab3.healthcheck
   ```
   Wypisuje wersję Postgresa, dostępność `pg_trgm`, wersję Solra, tryb pracy (SolrCloud), heap JVM i listę kolekcji.

## Narzędzia
- Solr Admin UI: <http://localhost:8983/solr>
- Zatrzymanie: `docker compose down` (dane zostają w wolumenach); pełny reset: `docker compose down -v`.

## Struktura
Opis katalogów i ustaleń projektu: `CLAUDE.md`. Treść zadania: `docs/Lab3.pdf`.
