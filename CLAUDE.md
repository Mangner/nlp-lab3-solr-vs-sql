# CLAUDE.md — Lab 3 PJN: wyszukiwanie pełnotekstowe, SQL kontra Solr

## Opis projektu
Laboratorium z przetwarzania języka naturalnego (treść: `docs/Lab3.pdf`). Porównujemy LIKE, indeks pełnotekstowy
PostgreSQL (tsvector + GIN) i Apache Solr 10 — funkcjonalnie i wydajnościowo — na metadanych arXiv.
Realizujemy **poziom 5.0** (czyli 3.0 + 4.0 + 5.0). Oddajemy: kod, skrypty SQL, schemat Solra (JSON), README
i sprawozdanie PDF (archiwum `LAB3_Nazwisko_Imie_Nazwisko_Imie.zip`, bez zbioru danych).

## Ustalenia (nie zmieniać bez pytania użytkownika)
- Język: Python 3.11+. Wszystko działa na Windows/macOS/Linux — żadnych skryptów bash/Makefile jako jedynej drogi;
  punkt wejścia to `python -m lab3.<moduł>` albo `scripts/*.py`.
- Infrastruktura: Docker Compose, dwa kontenery: `postgres:17` (część SQL) i `solr:10` (SOLR_HEAP=2g).
  Python działa na hoście i łączy się przez porty Postgresa (domyślnie 5432) i 8983.
- Dane: metadane arXiv (Cornell, CC0), mirror HF `librarian-bots/arxiv-metadata-snapshot` (parquet).
  Domyślnie 1 000 000 rekordów (`NUM_RECORDS`), bez danych osobowych (pomijamy authors, authors_parsed, submitter).
  Pola: id (arXiv id, klucz), title, abstract, primary_category (pierwsza z categories), archive (część
  primary_category przed kropką, np. "cs", "math", "hep-th"), categories (lista), year (rok pierwszej wersji), license.
- Postgres: kolumna tsvector (konfiguracja 'english', setweight: title A, abstract B) + indeks GIN; rozszerzenie pg_trgm.
- Solr: własny schemat przez Schema API, `update.autoCreateFields=false`; title/abstract = text_en;
  primary_category/archive/license = string (docValues); categories = string multiValued; year = pint.
  Ładowanie przez /update paczkami JSON po 5 000 dok., jeden commit na końcu.
- Skalowanie (5.0): 10% / 50% / 100% jako OSOBNE tabele (papers_10, papers_50, papers_100) w Postgresie i OSOBNE
  kolekcje (papers_10, papers_50, papers_100) w Solrze. Zbiory mniejsze są podzbiorami większych.
- Rozszerzenia: 4.0 — boost trafności rokiem; 5.0 — głębokie stronicowanie start/rows vs cursorMark oraz aktualizacja
  danych (zmiana/usunięcie w Postgresie → skrypt synchronizujący → weryfikacja zgodności).
- Konfiguracja w `.env` (python-dotenv); w repo tylko `.env.example`.
- README, komentarze i komunikaty dla użytkownika po polsku; nazwy w kodzie po angielsku.

## Plan etapów
- [x] 1. Szkielet projektu i infrastruktura
- [x] 2. Pobranie i przygotowanie danych
- [x] 3. PostgreSQL: schemat, COPY, tsvector + GIN, pomiary ładowania
- [x] 4. Solr: kolekcje, schemat, loader, pomiary indeksowania
- [x] 5. Zapytania poziomu 3.0 + tabela wyników
- [ ] 6. Poziom 4.0: ranking, GROUP BY, eDisMax, facety, highlighting, porównanie top-10, benchmark (mediana z 5), boost
- [ ] 7. Poziom 5.0: skalowanie 10/50/100%, facety + facet.range vs GROUP BY, cursorMark, synchronizacja zmian
- [ ] 8. Wykresy, README, informacje o sprzęcie/wersjach, materiały do sprawozdania, archiwum do oddania

Na końcu każdego etapu aktualizuj ten plik (checkbox, wnioski, nowe pliki).

## Struktura katalogów
```
docker-compose.yml     Postgres 17 + Solr 10
requirements.txt       zależności Pythona
.env.example / .env    konfiguracja (.env lokalny, w .gitignore)
lab3/                  pakiet Pythona
  config.py            odczyt .env -> obiekt `config` (pg_dsn, solr_url, num_records, ścieżki...)
  db.py                pg_connect() — połączenie psycopg 3
  solr.py              solr_get() — GET z wt=json
  healthcheck.py       python -m lab3.healthcheck
sql/                   skrypty SQL
solr/                  schemat dla Schema API (JSON)
scripts/               skrypty uruchamiane bezpośrednio
data/                  dane (w .gitignore); w kontenerze Postgresa montowane jako /data (ro)
results/               pomiary CSV/JSON, wykresy
docs/                  Lab3.pdf, materiały do sprawozdania
```

## Konwencje
- Moduły uruchamiamy jako `python -m lab3.<moduł>` z katalogu głównego (venv: `venv/`).
- Konfiguracja zawsze przez `lab3.config.config`, bez twardo wpisanych hostów/haseł.
- Pomiary: czas z drugiego+ uruchomienia (rozgrzany cache), mediana z 5; zapisujemy dokładne zapytanie/URL,
  liczbę wyników i czas (SQL: EXPLAIN (ANALYZE, BUFFERS); Solr: QTime + czas klienta).
- Powielanie danych niepotrzebne (arXiv ma >2 mln rekordów); gdyby użyte — oznaczać polem copy_no.

## Wnioski ze środowiska (zweryfikowane w etapie 1)
- **Tryb Solra:** obraz `solr:10` (Solr 10.1.0, Lucene 10.4.0) startuje domyślnie w **SolrCloud** z wbudowanym
  ZooKeeperem (log: "Starting in cloud mode", `/solr/admin/info/system` → `mode: solrcloud`). Nie trzeba żadnej
  flagi. Działają Configsets API (`/solr/admin/configs?action=LIST`, `/api/configsets`; w liście `_default`)
  i Collections API → można tworzyć kolekcje z własnym configsetem (kopia `_default`), jak na wykładzie.
- Solr z domyślnym heapem 2g: `jvm.memory.max` = 2 GB.
- Postgres 17.12; pg_trgm da się utworzyć (obraz zawiera contrib).
- Na maszynie autora port 5432 jest zajęty przez inny kontener (`magazyn_v20-db-1`), dlatego lokalny `.env` ma
  `PG_PORT=5433` (docker-compose mapuje host:`${PG_PORT}` -> 5432 w kontenerze). `.env.example` ma 5432.
- Docker Desktop: 12 CPU, ~15.6 GB RAM. Python hosta: 3.13.
- Healthcheck: wyjście przez potok na Windows może mieć zniekształcone polskie znaki (kodowanie konsoli) — w terminalu OK.

## Wnioski z etapów 2–3 (zrobione)
- **Etap 2** (`lab3/prepare_data.py`): HF mirror = 11 plików parquet (`data/train-*.parquet`, ~2,6 GB, kolumny jak w oryginale
  Kaggle: `versions` = lista struct{version, created "Mon, 7 Dec 1998 12:07:38 GMT"}, `update_date` = timestamp). Rok = min rok z versions[].created.
  Źródło: 3 224 635 rekordów; w źródle są **powtórzone id (83)** — deduplikacja (pierwsze wystąpienie); po filtrach (abstrakt ≥300 zn., rok) 3 093 551;
  wybrano 1 000 000 deterministycznie (blake2b(seed:id), najmniejsze klucze), 10% i 50% = N/10 i N/2 najmniejszych kluczy.
  Pliki: `data/papers_{10,50,100}.{csv,jsonl}`, surowe parquet w `data/raw/` (można skasować po przygotowaniu), `results/dataset_stats.json`.
- **Etap 3** (`lab3/load_pg.py`, `sql/01_schema.sql`, `sql/02_indexes.sql` — szablony z `{t}`): COPY klientem (STDIN) z tqdm; osobno mierzone COPY / GIN / B-tree / ANALYZE;
  `results/load_pg.json`. Tabele mają też `updated_at` (pod synchronizację w etapie 7).
- **Uwaga Solr/SolrCloud:** schemat i config leżą w configsecie w ZooKeeperze współdzielonym przez kolekcje — dlatego każda kolekcja ma własny
  configset `lab3_papers_<N>` (kopia `_default`). Domyślny `_default` ma autoCommit 15 s i autoSoftCommit 3 s — wyłączone w `solr/collection_config.json`
  (żeby był jeden commit na końcu).
- Solr text_en = Porter (porterStem) + stoplista Lucene; PG 'english' = snowball (Porter2) + inna stoplista — źródło różnic w liczbach trafień.
- Windows: heredoc w Bash potrafi się wywrócić przy długich plikach — pliki tworzyć narzędziem Write. Nie zabijać `python.exe` globalnie.

## Wnioski z etapów 4–5 (zrobione)
- **Etap 4**: `lab3/load_solr.py` (`--settle-only` = ponowny pomiar rozmiaru po scaleniu segmentów), `solr/schema.json`, `solr/collection_config.json`.
  Zaraz po commicie indeks 100% miał 2,2 GB (trwał merge, stare segmenty jeszcze na dysku) — po dodatkowym commicie 1241 MiB; w `load_solr.json`
  są oba pola (`index_bytes`, `index_bytes_settled`). Tlog 100% ≈ 1,2 GB (autoCommit wyłączony).
- **Etap 5**: `lab3/queries.py` (definicje Q1–Q3 + wariant z fq), `lab3/level3.py` -> `results/level3*.json`, `level3_table.md`, `docs/zapytania_solr.md`,
  `results/explain/`. Zapytania: Q1 simulate, Q2 "dark matter", Q3 galaxy AND (cluster OR merger) AND NOT simulation — wszystkie mają tysiące trafień.
  LIKE = parallel seq scan (~4,6 s na 1 mln), FTS = Bitmap Index Scan na GIN. Różnice FTS vs Solr (kilkadziesiąt dok. na ~10^5) wynikają z tokenizacji:
  PG parser traktuje `simulation/data` jako token typu file, URL-e jako url/host/url_path, rozbija `local_qasm_simulator` na części
  (Solr StandardTokenizer: underscore nie dzieli słów), `matter-wave` -> `matter-wav`+`matter`. Przykłady w `results/level3_diffs.json`.
- Cache wyników Solra: `{!cache=false}` vs domyślnie — QTime 0–4 ms vs 1 ms; pomiary robimy na domyślnej konfiguracji (opis w sprawozdaniu).
