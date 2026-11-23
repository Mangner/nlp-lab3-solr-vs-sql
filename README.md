# Laboratorium nr 3 — poziom 3.0

**Wyszukiwanie pełnotekstowe: SQL kontra Solr** (przedmiot: Przetwarzanie języka naturalnego, Politechnika Krakowska).

Autorzy: Michał Langner, Jakub Nawrocki.

Porównujemy trzy sposoby przeszukiwania tekstu — `LIKE '%…%'`, indeks pełnotekstowy PostgreSQL (`tsvector` + GIN)
i Apache Solr 10 — na metadanych publikacji arXiv: te same dane, te same trzy zapytania, liczba wyników i czas.

## Dane

- Źródło: metadane arXiv (Cornell University), **licencja CC0**; używamy kopii na Hugging Face:
  [`librarian-bots/arxiv-metadata-snapshot`](https://huggingface.co/datasets/librarian-bots/arxiv-metadata-snapshot) (pliki parquet, pobierane skryptem — **zbioru nie ma w repozytorium ani w archiwum**).
- **1 000 000 rekordów** wybranych deterministycznie (stały seed) z ok. 3 mln dostępnych; dane nie są powielane.
- **Bez danych osobowych:** pomijamy pola `authors`, `authors_parsed` i `submitter`.
- Pola: `id` (identyfikator arXiv, klucz), `title`, `abstract`, `primary_category`, `archive`, `categories`, `year`, `license`.

## Wymagania

- Docker Desktop (Windows/macOS) lub Docker Engine (Linux) z `docker compose`; min. 6 GB RAM dla Dockera (testowano na 16 GB).
- Python 3.11+ (testowano na 3.13).
- Wolne miejsce na dysku: ok. 15 GB (parquet ok. 2,6 GB, CSV/JSONL ok. 4 GB, wolumeny Postgresa i Solra ok. 5 GB).
- Wolne porty: 5432 (Postgres; można zmienić `PG_PORT`) i 8983 (Solr).

## Uruchomienie krok po kroku

Wszystkie polecenia z katalogu głównego projektu; działają na Windows / macOS / Linux.

1. **Kontenery** (PostgreSQL 17 i Solr 10, `SOLR_HEAP=2g`)
   ```
   cp .env.example .env          # Windows: copy .env.example .env
   docker compose up -d
   docker compose ps             # poczekaj na status "healthy" obu usług
   ```
   Jeśli port 5432 jest zajęty, ustaw w `.env` inny `PG_PORT` (np. `5433`).
2. **Środowisko Pythona**
   ```
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m lab3.healthcheck    # wersje, tryb SolrCloud, dostępność pg_trgm
   ```
3. **Dane, ładowanie i zapytania** (w tej kolejności):
   ```
   python -m lab3.prepare_data           # pobranie i przygotowanie danych (data/)
   python -m lab3.load_pg --sizes 100    # PostgreSQL: tabela papers_100, COPY, tsvector + GIN
   python -m lab3.load_solr --sizes 100  # Solr: kolekcja papers_100, schemat, indeksowanie
   python -m lab3.level3                 # zapytania Q1–Q3: LIKE / FTS / Solr, tabela wyników
   ```
   (`prepare_data` tworzy też podzbiory 10% i 50%, a `load_*` bez `--sizes` ładuje wszystkie trzy wielkości — do poziomu 3.0 wystarcza `papers_100`.)

   **Windows z Application Control.** Jeśli `python -m lab3.prepare_data` zgłasza błąd pyarrow „Zasady kontroli aplikacji zablokowały ten plik”,
   uruchom ten krok w kontenerze (pliki trafią do `data/` na hoście), a potem kontynuuj od `load_pg`:
   ```
   docker run --rm -v "${PWD}:/app" -w /app python:3.13 sh -c "pip install -q -r requirements.txt && python -m lab3.prepare_data"
   ```

Wyniki `level3` trafiają do `results/level3.json`, `results/level3_table.md`, `results/level3_diffs.json`, planów `results/explain/level3_*.txt`
oraz `docs/zapytania_solr.md` (zapytania Solra jako klikalne URL-e; Solr Admin UI: <http://localhost:8983/solr>).
Zatrzymanie: `docker compose down` (dane zostają w wolumenach); pełny reset: `docker compose down -v`.

## Struktura

```
docker-compose.yml     PostgreSQL 17 + Solr 10
requirements.txt       zależności Pythona
.env.example           konfiguracja (kopiujemy do .env)
lab3/                  config, db, solr, healthcheck, prepare_data, load_pg, load_solr, queries, measure, level3
sql/                   01_schema.sql (tabela + kolumna tsvector), 02_indexes.sql (GIN, B-tree) — szablony z {t} = nazwa tabeli
solr/                  schema.json (Schema API), collection_config.json (Config API)
docs/zapytania_solr.md zapytania Solra jako URL-e
results/               wyniki level3 (JSON, tabela, plany EXPLAIN)
```

## Wyniki (zbiór `papers_100`, 1 000 000 rekordów)

Zapytania (pola `title` + `abstract`): **Q1** — słowo `simulate` w dowolnej formie (+ wariant `LIKE '%simulate%'`), **Q2** — fraza `"dark matter"`,
**Q3** — `galaxy AND (cluster OR merger) AND NOT simulation`, **Q1+fq** — Q1 z filtrem `archive=astro-ph` i latami 2010–2020.
Czasy: mediana z 5 uruchomień po rozgrzewce; SQL — `EXPLAIN (ANALYZE, BUFFERS)`, Solr — `QTime` i czas klienta.

| zapytanie | wyniki LIKE | wyniki FTS (SQL) | numFound Solr | LIKE exec [ms] | FTS exec [ms] | FTS klient [ms] | Solr QTime [ms] | Solr klient [ms] | Solr QTime cache=false [ms] | Solr klient cache=false [ms] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1: słowo w dowolnej formie: simulate (simulated, simulates, simulating, simulation…) | 24333 | 119222 | 119255 | 4631.713 | 99.07 | 95.689 | 2.0 | 8.305 | 14.0 | 20.391 |
| Q2: fraza "dark matter" (słowa obok siebie, w tej kolejności) | 14655 | 14955 | 15025 | 4398.25 | 64.652 | 64.115 | 1.0 | 5.422 | 5.0 | 10.131 |
| Q3: galaxy AND (cluster OR merger) AND NOT simulation | 7259 | 8887 | 8918 | 4653.637 | 15.16 | 16.372 | 1.0 | 5.77 | 12.0 | 17.362 |
| Q1+fq: Q1 z filtrem: archive=astro-ph, lata 2010–2020 | 2138 | 9447 | 9449 | 370.941 | 83.301 | 85.348 | 1.0 | 4.965 | 5.0 | 9.292 |

Kolumny „Solr QTime” bez dopisku to zapytanie z domyślnym cache wyników (`queryResultCache`); „cache=false” to realne wykonanie zapytania.

## Podsumowanie wyników

**Liczba wyników.** `LIKE` szuka dosłownych podciągów, więc dla Q1 znajduje 24 333 dokumentów, a indeks pełnotekstowy 119 222: dzięki **stemmingowi**
`simulated`, `simulations`, `simulating` i `simulation` sprowadzają się do wspólnego rdzenia `simul`, a `LIKE '%simulate%'` ich nie dopasuje (za to złapie podciąg `resimulate`);
podobnie w Q2 (14 655 vs 14 955: `dark-matter` jest frazą dla FTS, ale nie dla `LIKE`) i w Q3 (7 259 vs 8 887: `galaxies` ≠ `galaxy`). Między PostgreSQL a Solrem różnica jest drobna
(Q1: 119 222 vs 119 255, Q2: 14 955 vs 15 025, Q3: 8 887 vs 8 918) i wynika z innej **tokenizacji** (PostgreSQL traktuje `simulation/data`, adresy URL i `local_qasm_simulator`
inaczej niż `StandardTokenizer` Solra, a `matter-wave` zaburza sąsiedztwo w frazie), innych **stoplist** (Lucene vs PostgreSQL) i wariantów stemmera Portera
(klasyczny Porter w Solrze, Snowball/Porter2 w PostgreSQL). Konkretne dokumenty: `results/level3_diffs.json`.

**Czasy.** `LIKE` wykonuje *Parallel Seq Scan* po całej tabeli (bez indeksu trigramowego), więc kosztuje ok. 4,4–4,7 s niezależnie od zapytania (4 632 / 4 398 / 4 654 ms dla Q1/Q2/Q3);
indeks GIN daje czasy 99 / 65 / 15 ms, czyli 47–307× szybciej (zależnie od liczby trafień — im mniej, tym szybciej). Solr jest jeszcze szybszy: `QTime` 1–2 ms z cache wyników
oraz 14 / 5 / 12 ms z wyłączonym cache (20 / 10 / 17 ms po stronie klienta, z narzutem HTTP), czyli 7× (Q1) i 13× (Q2) krócej niż FTS w SQL, a przy Q3 (mało trafień)
FTS w PostgreSQL (15 ms) jest porównywalny z Solrem bez cache (12 ms). Filtr strukturalny (Q1+fq) skraca `LIKE` do 371 ms, bo planista używa indeksu B-tree po `year`.

## Licencje i źródła

- Dane: metadane arXiv — CC0 (Cornell University, Kaggle `Cornell-University/arxiv`; kopia HF `librarian-bots/arxiv-metadata-snapshot`).
- Oprogramowanie: PostgreSQL 17 (licencja PostgreSQL), Apache Solr 10 (Apache 2.0), biblioteki Pythona wg `requirements.txt`.
