# Lab 3 (PJN) — wyszukiwanie pełnotekstowe: PostgreSQL kontra Solr

Porównanie trzech sposobów przeszukiwania tekstu — `LIKE '%…%'`, indeksu pełnotekstowego PostgreSQL (`tsvector` + GIN)
i Apache Solr 10 — funkcjonalnie i wydajnościowo, na metadanych publikacji arXiv. **Oddawany poziom: 3.0**.
Autorzy: Michał Langner, Jakub Nawrocki.

> **Zakres oddawanej pracy.** Oddajemy **poziom 3.0**: kod, skrypty SQL, schemat Solra oraz niniejszy README z instrukcją uruchomienia
> i tabelą wyników (sekcja *Wyniki poziomu 3.0*). Sprawozdanie (`docs/sprawozdanie.{md,pdf}`), ściąga ustna (`docs/odpowiedz_ustna.md`) oraz skrypty
> poziomów 4.0 (`lab3/level4.py`, `lab3/bench.py`, `lab3/cold.py`, boost rokiem) i 5.0 (`lab3/facets.py`, `lab3/paging.py`, `lab3/sync.py`, `sql/03_sync.sql`)
> są w repozytorium jako **materiał dodatkowy i nie są częścią oddawanej pracy**.

- Przedmiot: Przetwarzanie języka naturalnego, Politechnika Krakowska, prowadzący: dr inż. Wojciech Książek. Treść zadania: `docs/Lab3.pdf`.
- Materiał dodatkowy (poza oddawaną pracą): sprawozdanie `docs/sprawozdanie.pdf` (źródło: `docs/sprawozdanie.md`), ściąga do odpowiedzi ustnej `docs/odpowiedz_ustna.md`.
- Zapytania Solra jako klikalne URL-e: `docs/zapytania_solr.md`.

## Dane

- Źródło: metadane arXiv (Cornell University), **licencja CC0**; używamy kopii na Hugging Face:
  [`librarian-bots/arxiv-metadata-snapshot`](https://huggingface.co/datasets/librarian-bots/arxiv-metadata-snapshot) (pliki parquet, pobierane skryptem — **zbioru nie ma w repozytorium ani w archiwum**).
- Brak danych osobowych: pomijamy `authors`, `authors_parsed`, `submitter`.
- 1 000 000 rekordów (zbiór 100%) wybranych deterministycznie (stały seed; wymagane minimum poziomu 3.0 to 100 000). Skrypt przygotowania tworzy też podzbiory 10% i 50% — używa ich tylko materiał dodatkowy poziomu 5.0. Dane nie są powielane.
- Pola: `id`, `title`, `abstract`, `primary_category`, `archive`, `categories`, `year`, `license`.

## Wymagania

- Docker Desktop (Windows/macOS) lub Docker Engine (Linux) z `docker compose`; **min. 6 GB RAM** dla Dockera (testowano na 16 GB).
- Python 3.11+ (testowano na 3.13). Do zbudowania PDF: Chrome, Edge lub Chromium (jest w Windows 11) **albo** Docker (obraz `pandoc/latex`).
- Wolne miejsce na dysku: ok. 15 GB (pobrane parquet ok. 2,6 GB, pliki CSV/JSONL ok. 4 GB, wolumeny Postgresa i Solra ok. 5 GB).
- Wolne porty: 5432 (Postgres; można zmienić `PG_PORT`) i 8983 (Solr).

## Uruchomienie krok po kroku (od zera)

Wszystkie polecenia z katalogu głównego projektu. Skrypty są wieloplatformowe (Windows / macOS / Linux) — nie ma skryptów bash ani Makefile.

1. **Konfiguracja**
   ```
   cp .env.example .env          # Windows: copy .env.example .env
   ```
   Jeśli port 5432 jest zajęty, ustaw w `.env` inny `PG_PORT` (np. `5433`) — `docker-compose.yml` i kod Pythona czytają tę samą zmienną.
2. **Kontenery** (PostgreSQL 17 i Solr 10, `SOLR_HEAP=2g`)
   ```
   docker compose up -d
   docker compose ps             # poczekaj na status "healthy" obu usług
   ```
3. **Środowisko Pythona**
   ```
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m lab3.healthcheck    # wersje, tryb SolrCloud, dostępność pg_trgm
   ```
4. **Poziom 3.0 (oddawany) — wystarczą cztery kroki, w tej kolejności:**
   ```
   python -m lab3.prepare_data   # pobranie i przygotowanie danych
   python -m lab3.load_pg        # PostgreSQL: COPY, tsvector + GIN
   python -m lab3.load_solr      # Solr: kolekcje, schemat, indeksowanie
   python -m lab3.level3         # zapytania Q1–Q3: LIKE / FTS / Solr, tabela wyników
   ```
   **Windows:** jeśli `python -m lab3.prepare_data` zgłasza błąd pyarrow „Zasady kontroli aplikacji zablokowały ten plik”,
   przygotuj dane w Dockerze (pliki trafią do `data/` na hoście), a potem kontynuuj od `load_pg`:
   ```
   docker run --rm -v "${PWD}:/app" -w /app python:3.13 sh -c "pip install -q -r requirements.txt && python -m lab3.prepare_data"
   ```
5. **Opcjonalnie — wszystko jednym poleceniem** (także materiał dodatkowy poziomu 4.0: pomiary, wykresy, sprawozdanie, PDF; kilkadziesiąt minut do ok. 2 godzin)
   ```
   python -m lab3.run_all
   ```
   Opcje: `--limit 20000` (szybki test na małej próbce — uwaga: nadpisuje tabele/kolekcje i pliki w `results/`), `--skip prepare load_pg load_solr` (pomiń kroki),
   `--only figures report pdf` (tylko wybrane), `--with-cold` (pomiar zimnego startu — restartuje kontenery), `--extra` (dodatkowe kroki poziomu 5.0 — poza oddawaną pracą). Każdy krok jest idempotentny.

Kroki można też uruchamiać osobno:

| krok | polecenie | co robi | wynik |
|---|---|---|---|
| dane | `python -m lab3.prepare_data` | pobranie parquet z HF, filtrowanie, deduplikacja, wybór 10/50/100%, zapis CSV + JSONL | `data/papers_*.{csv,jsonl}`, `results/dataset_stats.json` |
| PostgreSQL | `python -m lab3.load_pg` | schemat (`sql/01_schema.sql`), `COPY`, GIN + B-tree (`sql/02_indexes.sql`), `ANALYZE`, pomiary | `results/load_pg.json` |
| Solr | `python -m lab3.load_solr` | kolekcje `papers_10/50/100`, schemat (`solr/schema.json`), paczki po 5000 dok., jeden commit | `results/load_solr.json` |
| poziom 3.0 | `python -m lab3.level3` | Q1–Q3 w LIKE / FTS / Solr, tabela, różnice w trafieniach | `results/level3*.json`, `docs/zapytania_solr.md` |
| benchmark (dodatkowy) | `python -m lab3.bench` | Q1–Q3 × (LIKE, FTS, Solr), mediana z 5; w sprawozdaniu używamy zbioru 100% | `results/benchmark.json` |
| poziom 4.0 (dodatkowy) | `python -m lab3.level4` | top-10 (`ts_rank_cd` vs eDisMax), GROUP BY vs facety (2 pola), highlighting, boost rokiem | `results/level4*.json` |
| zimny start | `python -m lab3.cold --drop-vm-cache` | pierwsze wykonanie po restarcie kontenerów | `results/cold.json` |
| środowisko | `python -m lab3.environment` | CPU, RAM, dysk, wersje, ustawienia | `results/environment.json` |
| wykresy | `python -m lab3.figures` | wykresy PNG (matplotlib) | `results/figures/` |
| sprawozdanie (dodatkowe) | `python -m lab3.report` → `python scripts/build_pdf.py` | `docs/sprawozdanie.md` z `results/`, potem PDF | `docs/sprawozdanie.pdf` |
| archiwum | `python scripts/pack_zip.py` | pakuje pliki do oddania: kod, `sql/`, `solr/`, README, `docs/zapytania_solr.md` (bez danych, `.env`, venv, sprawozdania i skryptów poziomu 5.0) | `dist/LAB3_Langner_Michal_Nawrocki_Jakub.zip` |

**Materiał dodatkowy (poziom 5.0, nie oddajemy; tylko w repozytorium, nie w archiwum):** `python -m lab3.facets` (2×`facet.field` + `facet.range` vs `GROUP BY`/`GROUPING SETS`),
`python -m lab3.paging` (`start/rows` vs `cursorMark` vs `OFFSET`), `python -m lab3.sync demo` (synchronizacja zmian PG → Solr), `python -m lab3.figures --extra` (wykresy skalowania, facetów, stronicowania).
Te skrypty zapisują wyniki do `results/` (`facets_vs_groupby.json`, `paging.json`, `sync_log.json`); `sync demo` zakłada triggery na `papers_100` (po demo dane są przywracane).

Narzędzia: Solr Admin UI — <http://localhost:8983/solr> (zakładka *Query*; URL-e z `docs/zapytania_solr.md` wklejamy w przeglądarkę).
Zatrzymanie: `docker compose down` (dane zostają w wolumenach); pełny reset: `docker compose down -v`.

## Struktura

```
docker-compose.yml     PostgreSQL 17 + Solr 10
requirements.txt       zależności Pythona
.env.example           konfiguracja (kopiujemy do .env)
lab3/                  pakiet Pythona: config, db, solr, healthcheck, prepare_data, load_pg, load_solr, queries, measure,
                       level3, level4, bench, cold, environment, figures, report, oral, run_all
                       (dodatkowo, poza oddawaną pracą — poziom 5.0: facets, paging, sync)
sql/                   01_schema.sql, 02_indexes.sql (szablony z {t} = nazwa tabeli; podstawia lab3); 03_sync.sql — tylko poziom 5.0 (dodatkowy)
solr/                  schema.json (Schema API), collection_config.json (Config API)
scripts/               build_pdf.py (sprawozdanie.md → PDF), pack_zip.py (archiwum do oddania)
data/                  dane (nie w repozytorium)
results/               pomiary JSON/MD, plany EXPLAIN, wykresy (results/figures)
docs/                  Lab3.pdf, sprawozdanie.{md,pdf}, zapytania_solr.md, odpowiedz_ustna.md
```

## Wyniki poziomu 3.0 (zbiór 100%, 1 000 000 rekordów)

Zapytania: **Q1** — słowo `simulate` w dowolnej formie (+ wariant `LIKE '%simulate%'`), **Q2** — fraza `"dark matter"`,
**Q3** — `galaxy AND (cluster OR merger) AND NOT simulation`, **Q1+fq** — Q1 z filtrem `archive=astro-ph`, lata 2010–2020. Pola: `title` + `abstract`.

<!-- TABELA30:START -->
| zapytanie | wyniki LIKE | wyniki FTS (SQL) | numFound Solr | czas LIKE [ms] | czas FTS [ms] | QTime Solr [ms] | QTime Solr, cache=false [ms] |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q1: słowo w dowolnej formie: simulate (simulated, simulates, simulating, simulation…) | 24 333 | 119 222 | 119 255 | 4 754,9 | 120,1 | 0 | 6 |
| Q2: fraza "dark matter" (słowa obok siebie, w tej kolejności) | 14 655 | 14 955 | 15 025 | 4 629,6 | 66,2 | 0 | 3 |
| Q3: galaxy AND (cluster OR merger) AND NOT simulation | 7 259 | 8 887 | 8 918 | 4 856,8 | 15,1 | 0 | 4 |
| Q1+fq: Q1 z filtrem: archive=astro-ph, lata 2010–2020 | 2 138 | 9 447 | 9 449 | 400,6 | 98,7 | 0 | 2 |

Zbiór: `papers_100` (1 000 000 rekordów), mediana z 5 uruchomień po rozgrzewce; czas SQL z `EXPLAIN (ANALYZE, BUFFERS)`.
<!-- TABELA30:END -->

**Skąd różnice w liczbie wyników.** `LIKE` znajduje dosłowne podciągi (np. `simulate`, ale nie `simulation`; za to `resimulate`), a FTS — wszystkie formy
po stemmingu (`simulated`, `simulations`, `simulating` → `simul`), stąd wielokrotnie więcej wyników. Między PostgreSQL a Solrem różnica jest drobna (dziesiątki dokumentów na ~10^5):
wynika głównie z innej tokenizacji (parser PostgreSQL traktuje `simulation/data`, adresy URL i `local_qasm_simulator` inaczej niż `StandardTokenizer` Solra; słowo złożone
`matter-wave` zaburza sąsiedztwo w frazie), a także z innych stoplist i wariantów stemmera Portera. Konkretne dokumenty: `results/level3_diffs.json`, szczegóły: sprawozdanie, p. 5.2.
Czas Solra: `QTime` z drugiego uruchomienia (z `queryResultCache`, ~0 ms) oraz z wyłączonym cache wyników (`cache=false`); `LIKE` to *Parallel Seq Scan* po całej tabeli
(bez indeksu trigramowego), FTS — *Bitmap Index Scan* na GIN.

## Licencje i źródła

- Dane: metadane arXiv — CC0 (Cornell University, Kaggle `Cornell-University/arxiv`; kopia HF `librarian-bots/arxiv-metadata-snapshot`).
- Oprogramowanie: PostgreSQL 17 (licencja PostgreSQL), Apache Solr 10 (Apache 2.0), biblioteki Pythona wg `requirements.txt`.
