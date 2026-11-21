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
- [ ] 2. Pobranie i przygotowanie danych
- [ ] 3. PostgreSQL: schemat, COPY, tsvector + GIN, pomiary ładowania
- [ ] 4. Solr: kolekcje, schemat, loader, pomiary indeksowania
- [ ] 5. Zapytania poziomu 3.0 + tabela wyników
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
