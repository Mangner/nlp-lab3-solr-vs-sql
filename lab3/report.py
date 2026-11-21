"""Etap 8: generuje docs/sprawozdanie.md oraz uzupełnia tabelę wyników w README.md — wyłącznie z plików results/.

Uruchomienie:  python -m lab3.report [--authors "Imię Nazwisko" "Imię Nazwisko"]
Wszystkie liczby w tekście pochodzą z results/*.json (generowanych przez skrypty pomiarowe). Komentarze
interpretacyjne są pisane na podstawie tych liczb; wartości wstawiane są automatycznie, żeby nie rozjechały się z danymi.
"""
import argparse
import json
import re
import sys

from lab3.config import ROOT, config

R = config.results_dir


def J(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


def n(x, d=0):
    """Liczba z separatorem tysięcy (spacja) i przecinkiem dziesiętnym."""
    s = f"{x:,.{d}f}".replace(",", " ")
    return s.replace(".", ",")


def mib(b):
    return n(b / 2**20)


def table(head, rows, align=None):
    align = align or ["---"] * len(head)
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(a if a.startswith(":") or a.endswith(":") else "---" for a in align) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def short(t, k=70):
    return t if len(t) <= k else t[: k - 1] + "…"


def md_escape(t):
    return t.replace("|", "\\|")


def build(authors: list[str]) -> str:
    ds = J("dataset_stats.json")
    d100, d50, d10 = (ds["datasets"][f"papers_{s}"] for s in ("100", "50", "10"))
    env = J("environment.json")
    lpg, lsr = J("load_pg.json"), J("load_solr.json")
    l3, l3d = J("level3.json"), J("level3_diffs.json")["diffs"]
    l4, bo = J("level4.json")["queries"], J("level4_boost.json")["queries"]
    bm = J("benchmark.json")
    cold = J("cold.json")
    fv = J("facets_vs_groupby.json")
    pg = J("paging.json")
    sy = J("sync_log.json")
    pgt = {t["table"]: t for t in lpg["tables"]}
    srt = {c["collection"]: c for c in lsr["collections"]}

    def m(size, q, mode, meth):
        return next(x for x in bm["measurements"] if x["size"] == size and x["query_key"] == q and x["mode"] == mode and x["method"] == meth)

    def sv(x):  # czas serwera
        return x["exec_ms"]["median"] if "exec_ms" in x else x["qtime_ms"]["median"]

    def cl(x):
        return x["client_ms"]["median"]

    o = []
    A = o.append
    # ------------------------------------------------------------------ strona tytułowa
    A(f"""<div class="title-page">
<p class="uni">Politechnika Krakowska</p>
<h1>Wyszukiwanie pełnotekstowe: SQL kontra Solr</h1>
<p class="sub">Laboratorium nr 3 — poziom 5.0</p>
<p class="sub">Przedmiot: Przetwarzanie języka naturalnego</p>
<p class="sub">Prowadzący: dr inż. Wojciech Książek</p>
<p class="authors">Autorzy: {", ".join(a.replace("<", "&lt;").replace(">", "&gt;") for a in authors)}</p>
<p class="date">Dane i pomiary z: {bm['timestamp'][:10]}</p>
</div>

<div class="pb"></div>

[TOC]

<div class="pb"></div>
""")
    # ------------------------------------------------------------------ 1. wstęp
    A(f"""## 1. Cel i zakres

Porównujemy trzy sposoby przeszukiwania tekstu: `LIKE '%…%'`, indeks pełnotekstowy PostgreSQL (kolumna `tsvector` + indeks GIN)
i Apache Solr 10 — funkcjonalnie i wydajnościowo, na metadanych publikacji arXiv. Zrealizowano poziom 5.0, czyli wymagania
poziomów 3.0 i 4.0 oraz skalowanie (10% / 50% / 100% danych), porównanie facetów z `GROUP BY` i dwa rozszerzenia z listy poziomu 5.0
(głębokie stronicowanie `cursorMark` i aktualizacja danych z synchronizacją do Solra) oraz rozszerzenie z listy 4.0 (boost trafności rokiem).
Każda liczba w tym sprawozdaniu pochodzi z plików w katalogu `results/` wygenerowanych przez skrypty projektu.
""")
    # ------------------------------------------------------------------ 2. zbiór
    ex = ds["example_record"]
    A(f"""## 2. Zbiór danych

- **Źródło:** metadane arXiv udostępnione przez Cornell University (Kaggle `Cornell-University/arxiv`), my korzystamy z kopii
  na Hugging Face: `{ds['source']}` (pliki parquet).
- **Licencja:** metadane arXiv są udostępnione na licencji **CC0**. Nie używamy danych osobowych: pomijamy pola `authors`,
  `authors_parsed` i `submitter`.
- **Liczba rekordów:** źródło zawiera {n(ds['source_records'])} rekordów; po usunięciu {n(ds['duplicate_ids_dropped'])} powtórzonych `id`
  oraz filtrach (abstrakt ≥ {ds['min_abstract_chars']} znaków, znany rok) zostaje {n(ds['records_after_filters'])}.
  Zbiór 100% to **{n(d100['records'])}** rekordów wybranych deterministycznie (skrót blake2b z `seed:id`, seed = {ds['seed']});
  zbiory 50% ({n(d50['records'])}) i 10% ({n(d10['records'])}) to podzbiory (10% ⊂ 50% ⊂ 100%).
- **Dane nie były powielane** (nie ma pola `copy_no`; arXiv ma ponad 3 mln rekordów, więc nie było takiej potrzeby).
- **Pola:** `id` (klucz, identyfikator arXiv), `title`, `abstract` (tekst), `primary_category` (pierwsza z `categories`), `archive`
  (część `primary_category` przed kropką), `categories` (lista), `year` (rok pierwszej wersji), `license`.
- **Rozmiar:** średnia długość abstraktu {n(d100['abstract_len_mean'], 1)} znaków (mediana {n(d100['abstract_len_median'])});
  CSV {mib(d100['csv_bytes'])} MiB, JSONL {mib(d100['jsonl_bytes'])} MiB (zbiór 100%).
- **Pola kategoryczne:** `primary_category` — {d100['distinct_primary_category']} wartości, `archive` — {d100['distinct_archive']},
  `license` — {d100['distinct_license']}. **Pole liczbowe:** `year` ({d100['year_distribution'][0][0]}–{d100['year_distribution'][-1][0]}).

Największe archiwa (zbiór 100%): {", ".join(f"{a} ({n(c)})" for a, c in d100['top_archive'][:6])}.

**Przykładowy rekord:**

```json
{json.dumps(ex, ensure_ascii=False, indent=1)}
```
""")
    # ------------------------------------------------------------------ 3. środowisko
    pgs = env["postgres"]["settings"]
    A(f"""## 3. Środowisko i metodyka pomiarów

| element | wartość |
|---|---|
| procesor | {env['cpu']} ({env['cpu_cores_physical']} rdzeni, {env['cpu_threads']} wątków) |
| pamięć RAM | {env['ram_gb']} GB (Docker: {env['docker_resources']}) |
| dysk | {"; ".join(f"{d['FriendlyName']} ({d['MediaType']})" for d in env['disk'].get('physical_disks', [])) or "—"} (dane na dysku systemowym, {env['disk']['total_gb']} GB) |
| system | {env['os']} |
| Docker | {env['docker_version']} (Docker Desktop) |
| PostgreSQL | {env['postgres']['version']}; `shared_buffers`={pgs['shared_buffers']}, `work_mem`={pgs['work_mem']}, `maintenance_work_mem`={pgs['maintenance_work_mem']}, `effective_cache_size`={pgs['effective_cache_size']}, `max_parallel_workers_per_gather`={pgs['max_parallel_workers_per_gather']}, JIT={pgs['jit']} |
| Solr | {env['solr']['version']} (Lucene {env['solr']['lucene']}), tryb {env['solr']['mode']} (wbudowany ZooKeeper), `SOLR_HEAP`={env['solr']['SOLR_HEAP']} (max sterta JVM {env['solr']['jvm_max_heap_gb']} GB), {env['solr']['jvm']} |
| Python | {env['python']} (klient: psycopg 3, requests) |

**Metodyka.** Te same dane i te same zapytania w obu systemach. Czasy pochodzą z uruchomień po rozgrzewce (1 uruchomienie
rozgrzewające + {bm['repeats']} pomiarów; podajemy medianę, w plikach JSON także minimum i maksimum). Dla SQL mierzymy
(a) *Execution Time* z `EXPLAIN (ANALYZE, BUFFERS)` — czas serwera — oraz (b) czas po stronie klienta (wykonanie + pobranie wyniku);
dla Solra (a) `QTime` z odpowiedzi (rozdzielczość 1 ms) oraz (b) czas klienta (HTTP + JSON, połączenie utrzymywane — `requests.Session`).
Przy każdym pomiarze zapisujemy dokładne zapytanie (pełny SQL lub pełny URL), liczbę wyników, czas i znacznik czasu
(`results/*.json`). Plany `EXPLAIN` zapytań poziomu 3.0 są w `results/explain/`.

**Cache wyników Solra.** Powtórzone identyczne zapytanie jest w Solrze obsługiwane z `queryResultCache` (QTime ≈ 0 ms), co nie mierzy
kosztu dopasowania i rankingu. Dlatego w benchmarku mierzymy Solra w dwóch wariantach: `cache=false` (parametr lokalny
`{{!lucene cache=false}}` / `{{!edismax … cache=false}}` — realne wykonanie) oraz domyślnym (z cache). **W wykresach i wnioskach
używamy wariantu `cache=false`** (a cache pokazujemy osobno). Cache plików systemu operacyjnego jest w obu systemach rozgrzany.

**LIKE.** `LIKE` jest zwykłym skanem tabeli — **nie** założyliśmy indeksu trigramowego (`gin_trgm_ops`), choć rozszerzenie `pg_trgm` jest
zainstalowane. Plan: *Parallel Seq Scan* (do {pgs['max_parallel_workers_per_gather']} procesów roboczych + proces główny; dla zapytania
z filtrem po `year`/`archive` planista wybiera inny plan).
""")
    # ------------------------------------------------------------------ 4. schematy
    schema_sql = (ROOT / "sql" / "01_schema.sql").read_text(encoding="utf-8").replace("{t}", "papers_100")
    idx_sql = "\n".join(l for l in (ROOT / "sql" / "02_indexes.sql").read_text(encoding="utf-8").replace("{t}", "papers_100").splitlines()
                        if not l.startswith("-- @"))
    schema_json = (ROOT / "solr" / "schema.json").read_text(encoding="utf-8")
    cfg_json = (ROOT / "solr" / "collection_config.json").read_text(encoding="utf-8")
    A(f"""## 4. Schemat w SQL i w Solrze

### 4.1. PostgreSQL: tabela i indeks pełnotekstowy

Trzy osobne tabele `papers_10`, `papers_50`, `papers_100` (poniżej `papers_100`):

```sql
{schema_sql.strip()}
```

Indeksy zakładamy **po** załadowaniu danych (szybciej niż przy `COPY`):

```sql
{idx_sql.strip()}
```

Kolumna `tsv` jest `GENERATED … STORED`: tsvector liczy się przy `INSERT`/`COPY`/`UPDATE` automatycznie (konfiguracja `english` =
stoplista angielska + stemmer Snowball/Porter2); tytuł ma wagę A, abstrakt B. Indeks GIN to indeks odwrócony: dla każdego leksemu
lista wierszy, w których występuje. Zapytania używają operatora `@@` (np. `tsv @@ phraseto_tsquery('english','dark matter')`).

### 4.2. Solr: schemat (Schema API) i uzasadnienie flag

Każda kolekcja (`papers_10/50/100`) ma własny configset (kopia `_default`), wyłączone tworzenie pól „w locie”
(`update.autoCreateFields=false` — dokument z nieznanym polem jest odrzucany, sprawdziliśmy to) i wyłączone `autoCommit`/`autoSoftCommit`
(jeden commit na końcu ładowania). Plik `solr/schema.json`:

```json
{schema_json.strip()}
```

Konfiguracja kolekcji (`solr/collection_config.json`):

```json
{cfg_json.strip()}
```

| pole | typ | indexed | stored | docValues | multiValued | uzasadnienie |
|---|---|:-:|:-:|:-:|:-:|---|
| `id` | string (uniqueKey) | tak | tak | tak | nie | klucz; wyszukiwanie/usuwanie po id, sortowanie pomocnicze (`id asc`) w `cursorMark` |
| `title` | text_en | tak | tak | — | nie | przeszukiwanie z wagą (`qf=title^3`), `stored` do wyświetlania i podświetlania; docValues nie dotyczy pól analizowanych |
| `abstract` | text_en | tak | tak | — | nie | j.w.; `stored` konieczne dla `hl` (unified highlighter odczytuje tekst z pola stored) |
| `text_all` | text_en | tak | **nie** | — | tak | pole zbiorcze (`copyField` z `title` i `abstract`) dla zapytań poziomu 3.0; nie wyświetlamy go, więc `stored=false` oszczędza miejsce |
| `primary_category` | string | tak | tak | tak | nie | filtry `fq` (indexed), facety i sortowanie (docValues), wyświetlanie (stored) |
| `archive` | string | tak | tak | tak | nie | j.w. |
| `license` | string | tak | tak | tak | nie | j.w. |
| `categories` | string | tak | tak | tak | **tak** | rekord ma listę kategorii; facet po wszystkich kategoriach, filtr po dowolnej |
| `year` | pint | tak | tak | tak | nie | zakresy `fq=year:[a TO b]` (indexed, struktura punktowa), `facet.range`, sortowanie i funkcja `boost` (docValues) |

### 4.3. Łańcuch analizy `text_en`

Typ `text_en` ze schematu `_default` (Solr {env['solr']['version']}). **Indeksowanie:** tokenizer `standard` → filtr stop (`lang/stopwords_en.txt`) →
`lowercase` → `englishPossessive` (obcina `'s`) → `keywordMarker` (chroni słowa z `protwords.txt`) → `porterStem`.
**Zapytania:** to samo, z dodatkowym filtrem `synonymGraph` (`synonyms.txt`) na początku.

Porównanie z PostgreSQL (`english`): ten sam pomysł (tokenizacja → małe litery → stoplista → stemming), ale **inne komponenty**:
PostgreSQL używa *parsera* tekstu rozpoznającego typy tokenów (URL, plik, host, słowo złożone z myślnikiem, liczba), słownika Snowball
(Porter2) i własnej stoplisty; Solr — tokenizera Unicode (UAX#29) i klasycznego algorytmu Portera. To źródło różnic opisanych w p. 5.2.

""")
    # ------------------------------------------------------------------ 5. porównanie funkcjonalne
    rows = l3["rows"]
    t3 = [[f"**{r['key']}** {r['title']}", n(r["like"]["result_count"]), n(r["fts"]["result_count"]), n(r["solr"]["result_count"]),
           n(r["like"]["exec_ms"]["median"], 1), n(r["fts"]["exec_ms"]["median"], 1),
           n(r["solr"]["qtime_ms"]["median"], 0), n(r["solr_nocache"]["qtime_ms"]["median"], 0), n(r["solr_nocache"]["client_ms"]["median"], 1)]
          for r in rows]
    table30 = table(["zapytanie", "wyniki LIKE", "wyniki FTS (SQL)", "numFound Solr", "czas LIKE [ms]", "czas FTS [ms]",
                     "QTime Solr [ms] (cache)", "QTime Solr [ms] (cache=false)", "klient Solr [ms] (cache=false)"], t3,
                    ["---", "---:", "---:", "---:", "---:", "---:", "---:", "---:", "---:"])
    A(f"""## 5. Porównanie funkcjonalne (poziom 3.0 i 4.0)

### 5.1. Zapytania i wyniki (zbiór 100%, {n(d100['records'])} rekordów)

Wszystkie zapytania dotyczą pól `title` i `abstract` (w Solrze `text_all`, w SQL `tsv`; LIKE: `(title || ' ' || abstract) ILIKE '%…%'`).

- **Q1** — słowo w dowolnej formie: `simulate` (SQL: `plainto_tsquery('english','simulate')`; Solr: `q=text_all:simulate`) + wariant `LIKE '%simulate%'`.
- **Q2** — fraza `dark matter` (SQL: `phraseto_tsquery`; Solr: `q=text_all:"dark matter"`).
- **Q3** — `galaxy AND (cluster OR merger) AND NOT simulation` (SQL: `to_tsquery('english','galaxy & (cluster | merger) & !simulation')`).
- **Q1+fq** — Q1 z filtrem `archive=astro-ph` i latami 2010–2020 (Solr: dwa `fq`; SQL: warunki `WHERE`).

Słowa wybraliśmy tak, by miały wyraźne formy fleksyjne i tysiące trafień; zapytania Solra jako klikalne URL-e są w `docs/zapytania_solr.md`.
Czas SQL = *Execution Time* z `EXPLAIN (ANALYZE, BUFFERS)`, mediana z 5.

{table30}

Czasy klienta SQL (mediana): {", ".join(f"{r['key']} — LIKE {n(r['like']['client_ms']['median'],1)} ms, FTS {n(r['fts']['client_ms']['median'],1)} ms" for r in rows)}.
`QTime` w Solrze ma rozdzielczość 1 ms; wariant „cache” zwraca wynik z `queryResultCache` (0 ms).

**Plany.** `LIKE` → {"Parallel Seq Scan" if rows[0]['like']['plan_flags']['parallel_seq_scan'] else "Seq Scan"} po całej tabeli;
FTS → *Bitmap Index Scan* na indeksie GIN + *Bitmap Heap Scan* (Q1: {n(rows[0]['fts']['result_count'])} wierszy).
Wariant `Q1+fq`: LIKE używa *Parallel Index Scan* po indeksie B-tree na `year` (zawęża zbiór do lat 2010–2020), a `LIKE` i `archive` sprawdza jako filtr
({n(rows[3]['like']['exec_ms']['median'],0)} ms zamiast {n(rows[0]['like']['exec_ms']['median'],0)} ms; patrz `results/explain/level3_Q1+fq_like.txt`). Tabela {n(pgt['papers_100']['table_bytes_with_toast']/2**20)} MiB
jest większa niż `shared_buffers` ({pgs['shared_buffers']}), więc skan `LIKE` czyta strony także z cache systemu operacyjnego (`Buffers: … read=…` w planie) — to też część jego kosztu.

### 5.2. Skąd różnice w liczbie wyników

""")
    def dd(k):
        return l3d[k]
    d1, d2, d3 = dd("Q1"), dd("Q2"), dd("Q3")
    A(f"""**FTS a LIKE.** `LIKE '%simulate%'` zwraca {n(d1['counts']['like'])} dokumentów, FTS {n(d1['counts']['fts'])}: indeks pełnotekstowy
znajduje wszystkie formy fleksyjne (po stemmingu `simulated`, `simulations`, `simulating`, `simulation` → `simul`), a `LIKE` tylko ciągi zawierające
dosłownie `simulate` (nie znajdzie `simulation`: {n(d1['fts_only_vs_like'])} dokumentów jest w FTS, a nie w LIKE).
Przykłady: 0704.0021 (*simulations*) i 0704.0022 (*simulating*) — są w FTS, nie ma ich w LIKE. Odwrotnie ({n(d1['like_only_vs_fts'])} dok.): `LIKE` znajduje
**podciągi**, np. 0709.3304 zawiera `resimulate` (stem `resimul`, inny niż `simul`). Podobnie w Q3 `LIKE '%cluster%'` łapie `supercluster`/`protocluster`
(np. 0706.1593, 0706.2865), których FTS nie uznaje za słowo `cluster` ({n(d3['like_only_vs_fts'])} dok. tylko w LIKE), a FTS znajduje formy takie jak `clusters`/`galaxies`
(np. 0704.0478, 0704.2057), których `LIKE` z dosłownym wzorcem `galaxy` nie dopasuje (`galaxies` ≠ `galaxy`): {n(d3['fts_only_vs_like'])} dok. tylko w FTS.
Dla frazy (Q2) `LIKE` wymaga dosłownie `dark matter` z jedną spacją, więc nie znajdzie `dark-matter` (np. 0705.0429, 0708.1987) ani `(dark) matter` (0708.2910), które FTS uznaje za frazę
({n(d2['fts_only_vs_like'])} dok. tylko w FTS); odwrotnie, `LIKE` dopasuje podciąg także wtedy, gdy słowo jest częścią tokenu złożonego, jak `energy/dark matter` (0711.4288) czy `dark matter-wave` (0712.1543), których FTS PostgreSQL nie uznaje za frazę ({n(d2['like_only_vs_fts'])} dok.).

**FTS (PostgreSQL) a Solr.** Różnica jest mała (Q1: {n(d1['fts_only'])} dok. tylko w SQL i {n(d1['solr_only'])} tylko w Solrze na {n(d1['counts']['fts'])};
Q2: {n(d2['fts_only'])} / {n(d2['solr_only'])} na {n(d2['counts']['fts'])}; Q3: {n(d3['fts_only'])} / {n(d3['solr_only'])} na {n(d3['counts']['fts'])})
i wynika z **tokenizacji**, nie ze stemmingu:

- **Tylko w Solrze:** 1008.1143 — tekst zawiera `simulation/data`; parser PostgreSQL rozpoznaje to jako jeden token typu *file*
  (`simulation/data`), więc nie ma w nim leksemu `simul`; tokenizer Solra dzieli na `/`. Podobnie 1208.3789 — słowo `simulator` ukryte w adresie
  `www2.cs.uic.edu/~dasgupta/financial-simulator-files`, który PostgreSQL traktuje jako *url*/*host*/*url_path*.
- **Tylko w PostgreSQL:** 1810.03390 — `local_qasm_simulator`: PostgreSQL dzieli na podkreślniku (`local`, `qasm`, `simul`), a `StandardTokenizer`
  Solra (UAX#29) **nie** dzieli na `_`, więc `simulator` nie jest osobnym tokenem. Podobnie 2207.07417 (`ms08_simulating_quantum_tensor_contraction`).
- **Fraza „dark matter”:** 0712.1543 zawiera `dark matter-wave` — w PostgreSQL słowo złożone `matter-wave` zajmuje kilka pozycji
  (`matter-wav`, `matter`, `wave`), więc `dark` i `matter` nie sąsiadują i fraza nie jest znaleziona; w Solrze `matter-wave` rozbija się na `matter` i `wave` kolejnych pozycji.
- **Q3 (tylko w Solrze):** 0710.0955 zawiera `clusters/groups`, 0801.1109 — `merger/interaction`, 0808.0461 — `interacting/merger`: PostgreSQL widzi to jako jeden token
  typu *file* (leksemy `cluster`/`merger` nie powstają, więc warunek `cluster | merger` nie jest spełniony), a Solr rozdziela na `/` i dokument pasuje.
- Pozostałe różnice: inne **stoplisty** (Lucene vs PostgreSQL) i różne warianty algorytmu Portera (Solr: klasyczny Porter, PostgreSQL: Snowball/Porter2) — mogą dawać
  inne stemy dla rzadkich słów.

Pełne listy przykładów są w `results/level3_diffs.json`.
""")
    # ------------------------------------------------------------------ 5.3 ranking
    A("### 5.3. Ranking top-10: `ts_rank_cd` (PostgreSQL) a eDisMax (Solr)\n")
    A("""SQL: `ts_rank_cd(tsv, query)` (wagi tsvector: A = 1,0 dla tytułu, B = 0,4 dla abstraktu), `ORDER BY rank DESC, id ASC LIMIT 10`.
Solr: `defType=edismax`, `qf=title^3 abstract`, dla frazy dodatkowo `pf=title^3 abstract`, `sort=score desc, id asc` (BM25). Pełne zapytania i URL-e są w `results/level4.json`.
""")
    for k, v in l4.items():
        rowsr = []
        for i in range(10):
            a, b = v["pg_top10"][i], v["solr_top10"][i]
            rowsr.append([i + 1, a["id"], n(a["score"], 2), a["year"], md_escape(short(a["title"], 45)),
                          b["id"], n(b["score"], 2), b["year"], md_escape(short(b["title"], 45))])
        A(f"**{k}** — {v['title']}. Wspólnych dokumentów w top-10: **{v['common_top10_count']}**, w top-100: **{v['common_top100_count']}**; "
          f"`ts_rank_cd` z normalizacją długości (flaga 2): top-10 **{v['common_top10_count_pg_norm2']}**, top-100 **{v['common_top100_count_pg_norm2']}**. "
          f"Średnia długość abstraktu w top-10: PG {n(v['mean_abstract_len_top10']['pg_ts_rank_cd'])}, PG norm. {n(v['mean_abstract_len_top10']['pg_norm2'])}, "
          f"Solr {n(v['mean_abstract_len_top10']['solr_edismax'])} znaków.\n")
        A(table(["#", "PG id", "ts_rank_cd", "rok", "tytuł (PG)", "Solr id", "BM25", "rok", "tytuł (Solr)"], rowsr,
                ["---:", "---", "---:", "---:", "---", "---", "---:", "---:", "---"]))
        A("")
    A(f"""**Wyjaśnienie różnic.** Zbiór trafień jest (prawie) ten sam, różni się **kolejność**:

- `ts_rank_cd` mierzy *gęstość i bliskość* wystąpień (*cover density*) i domyślnie **nie normalizuje długości** dokumentu — dłuższe abstrakty z wieloma wystąpieniami
  zdobywają wysokie wyniki. Włączenie normalizacji długości (flaga 2) zwiększa zgodność top-100 z Solrem z {l4['Q1']['common_top100_count']}/{l4['Q2']['common_top100_count']}/{l4['Q3']['common_top100_count']}
  do {l4['Q1']['common_top100_count_pg_norm2']}/{l4['Q2']['common_top100_count_pg_norm2']}/{l4['Q3']['common_top100_count_pg_norm2']} (Q1/Q2/Q3), ale nie do pełnej zgodności.
- BM25 (Solr) uwzględnia **IDF** (rzadkie słowa ważą więcej), **nasycenie częstości** (kolejne wystąpienia coraz mniej podnoszą wynik)
  i **normalizację długości pola** (krótki tytuł z trafieniem wygrywa) — stąd w Solrze na czele krótkie tytuły takie jak *Dark matter* (Q2).
- Różne **wagi pól**: `title^3` w eDisMax (mnożnik 3 względem abstraktu) kontra A = 1,0 i B = 0,4 w tsvectorze (stosunek 2,5) — oraz inne skale wyników (brak porównywalności wartości liczbowych).
- Solr dla frazy dodaje `pf` (premia za frazę w polu), a PostgreSQL ma frazę w samym `tsquery`.
""")
    # ------------------------------------------------------------------ 5.4 GROUP BY vs facety, hl
    A("### 5.4. `GROUP BY` w SQL i facety Solra dla wyników zapytania; podświetlanie\n")
    A("Dla każdego zapytania: agregacja `GROUP BY primary_category` / `archive` w PostgreSQL oraz `facet.field=primary_category&facet.field=archive` w Solrze (top-5 wartości):\n")
    for k, v in l4.items():
        g = v["group_by_vs_facets"]
        rr = []
        for i in range(5):
            rr.append([i + 1, g["primary_category"]["rows"][i][0], n(g["primary_category"]["rows"][i][1]),
                       g["primary_category"]["solr_facet"][i][0], n(g["primary_category"]["solr_facet"][i][1]),
                       g["archive"]["rows"][i][0], n(g["archive"]["rows"][i][1]), g["archive"]["solr_facet"][i][0], n(g["archive"]["solr_facet"][i][1])])
        A(f"**{k}**\n")
        A(table(["#", "SQL primary_category", "n", "Solr primary_category", "n", "SQL archive", "n", "Solr archive", "n"], rr,
                ["---:", "---", "---:", "---", "---:", "---", "---:", "---", "---:"]))
        A("")
    A("Liczności są zbliżone, lecz niezupełnie równe, bo zbiory trafień różnią się o kilkadziesiąt dokumentów (p. 5.2). Dla zbiorów wyznaczonych filtrem strukturalnym są identyczne (p. 8).\n")
    h = l4["Q2"]["highlighting"]
    first_solr = next(iter(h["solr"].items()))
    first_pg = h["pg_ts_headline"][0]
    sn = (first_solr[1] or {}).get("abstract") or (first_solr[1] or {}).get("title") or ["—"]
    A(f"""**Podświetlanie (Q2).** Solr: `hl=true&hl.fl=abstract,title&hl.method=unified&hl.snippets=2&hl.fragsize=220` (tag `<em>`), dokument `{first_solr[0]}`:

> {sn[0]}

PostgreSQL: `ts_headline('english', abstract, query, 'MaxFragments=2, MaxWords=35, MinWords=15')`, dokument `{first_pg['id']}`:

> {first_pg['ts_headline']}

Solr zwraca fragmenty razem z wynikiem w jednym żądaniu (unified highlighter, tekst z pola `stored`); PostgreSQL wymaga osobnego wywołania `ts_headline` na surowym tekście
(ponownie parsuje dokument — koszt rośnie liniowo z liczbą podświetlanych dokumentów; dla 10 dokumentów Q2: {n(h['pg_ts_headline_10docs_ms'],1)} ms). Fragmenty wybierane są inaczej
(Solr — okna wokół najgęstszych trafień, `ts_headline` — wg `MaxFragments/MinWords/MaxWords`), a znaczniki `<em>` ustawiamy w obu.
""")
    # ------------------------------------------------------------------ 6. pomiary
    A("## 6. Pomiary wydajności\n")
    A("### 6.1. Ładowanie i indeksowanie\n")
    A(table(["zbiór", "PG: COPY [s]", "PG: GIN [s]", "PG: B-tree×2 [s]", "PG: ANALYZE [s]", "PG: razem [s]", "Solr: wysyłanie [s]", "Solr: commit [s]", "Solr: razem [s]"],
            [[f"{s}% ({n(pgt['papers_'+s]['rows'])})", n(pgt['papers_'+s]['copy_seconds'], 1), n(pgt['papers_'+s]['gin_seconds'], 1),
              n(pgt['papers_'+s]['btree_year_seconds'] + pgt['papers_'+s]['btree_category_seconds'], 1), n(pgt['papers_'+s]['analyze_seconds'], 1),
              n(sum(pgt['papers_'+s][k] for k in ('copy_seconds', 'gin_seconds', 'btree_year_seconds', 'btree_category_seconds', 'analyze_seconds')), 1),
              n(srt['papers_'+s]['send_seconds'], 1), n(srt['papers_'+s]['commit_seconds'], 1), n(srt['papers_'+s]['total_seconds'], 1)] for s in ("10", "50", "100")],
            ["---", "---:", "---:", "---:", "---:", "---:", "---:", "---:", "---:"]))
    A(f"""
`COPY` w PostgreSQL zawiera obliczanie kolumny `tsv` (to ona jest kosztowna), indeks GIN budujemy osobno po załadowaniu. Solr: paczki po {srt['papers_100']['batch_size']} dokumentów JSON
na `/update`, jeden commit na końcu; po załadowaniu `numFound` = liczba wierszy w tabeli ({", ".join(f"{s}%: {n(srt['papers_'+s]['num_found'])}" for s in ("10", "50", "100"))}; zgodność: {'tak' if all(c['counts_match'] for c in lsr['collections']) else 'NIE'}).

![Czas ładowania i rozmiar na dysku](../results/figures/ladowanie.png)

Rozmiar na dysku (zbiór 100%): PostgreSQL — tabela z TOAST {mib(pgt['papers_100']['table_bytes_with_toast'])} MiB (zawiera tekst oraz kolumnę `tsv`, średnio {n(pgt['papers_100']['avg_tsv_bytes'])} B/wiersz),
indeks GIN {mib(pgt['papers_100']['gin_bytes'])} MiB, wszystkie indeksy {mib(pgt['papers_100']['indexes_bytes'])} MiB; Solr — indeks {mib(srt['papers_100']['index_bytes_settled'])} MiB po scaleniu segmentów
(zaraz po commicie {mib(srt['papers_100']['index_bytes'])} MiB — w tle trwał jeszcze merge, stare segmenty zostają na dysku do kolejnego commitu; plus dziennik transakcji `tlog`, bo `autoCommit` jest wyłączony).
""")
    # 6.2 tabele zapytań 100%
    A("### 6.2. Czasy zapytań (zbiór 100%, mediana z 5)\n")
    A("Tryb **count** — liczba trafień (SQL `SELECT count(*)`, Solr `rows=0`); tryb **top-10** — 10 najlepszych wg trafności (SQL `ts_rank_cd … LIMIT 10`, Solr eDisMax; `LIKE` nie ma rankingu).\n")
    rr = []
    for q in ("Q1", "Q2", "Q3"):
        for mode in ("count", "top10"):
            meths = ["LIKE", "FTS", "Solr", "Solr+cache"] if mode == "count" else ["FTS", "Solr", "Solr+cache"]
            for meth in meths:
                x = m("100", q, mode, meth)
                tm = x["exec_ms"] if "exec_ms" in x else x["qtime_ms"]
                rr.append([q, mode, {"LIKE": "LIKE", "FTS": "PostgreSQL FTS", "Solr": "Solr (cache=false)", "Solr+cache": "Solr (cache)"}[meth],
                           n(x["result_count"]) if mode == "count" else ("10 z " + n(x["result_count"]) if meth.startswith("Solr") else "10"),
                           n(tm["median"], 1), f"{n(tm['min'],1)}–{n(tm['max'],1)}", n(cl(x), 1)])
    A(table(["zapytanie", "tryb", "metoda", "wyniki", "czas serwera: mediana [ms]", "min–maks [ms]", "czas klienta: mediana [ms]"], rr,
            ["---", "---", "---", "---:", "---:", "---:", "---:"]))
    A("""
Czas serwera: SQL — *Execution Time* z `EXPLAIN ANALYZE`; Solr — `QTime` (rozdzielczość 1 ms, stąd wartości całkowite i „0”). Czas klienta zawiera narzut HTTP/JSON (Solr)
albo komunikacji z bazą (SQL). Dokładne zapytania i wszystkie pomiary: `results/benchmark.json`.

**Zimny start.** Metoda: `docker compose restart postgres solr` (czyści `shared_buffers` i pamięć JVM) oraz zrzut page cache maszyny wirtualnej Dockera
(`drop_caches` — wykonany: """ + ("tak" if cold["vm_page_cache_dropped"] else "nie") + """). Pierwsze wykonanie po restarcie, zbiór 100%, tryb count:
""")
    A(table(["zapytanie", "PG FTS: 1. wykonanie [ms]", "PG FTS: rozgrzany [ms]", "Solr: 1. wykonanie [ms]", "Solr: rozgrzany [ms]"],
            [[q,
              n(next(x for x in cold['results'] if x['query_key'] == q and x['method'] == 'FTS count')['first_run_client_ms'], 0),
              n(cl(m('100', q, 'count', 'FTS')), 1),
              n(next(x for x in cold['results'] if x['query_key'] == q and x['method'] == 'Solr count')['first_run_client_ms'], 0),
              n(cl(m('100', q, 'count', 'Solr')), 1)] for q in ("Q1", "Q2", "Q3")],
            ["---", "---:", "---:", "---:", "---:"]))
    A("\n![Zimny start a rozgrzany cache](../results/figures/zimny_start.png)\n")

    # ------------------------------------------------------------------ 7. rozszerzenia
    A("## 7. Rozszerzenia\n")
    A("### 7.1. Boost trafności rokiem (poziom 4.0)\n")
    A(f"""Cel: nowsze publikacje wyżej. Funkcja `f(year) = exp(0,08·(year − 2025))` — każdy rok wstecz zmniejsza wynik o ok. 8%.
Solr: parametr eDisMax `boost=exp(mul(0.08,sub(year,2025)))` (mnożnik wyniku BM25, pole `year` z docValues);
SQL: `ts_rank_cd(tsv, q) * exp(0.08 * (year - 2025))`. Zapytania i URL-e: `results/level4_boost.json`.
""")
    rr = []
    for k, v in bo.items():
        for eng, nm in (("pg", "PostgreSQL"), ("solr", "Solr")):
            b, a = v["year_stats"][f"{eng}_before"], v["year_stats"][f"{eng}_after"]
            rr.append([k, nm, n(b["top10_mean_year"], 1), n(a["top10_mean_year"], 1), n(b["top100_mean_year"], 1), n(a["top100_mean_year"], 1),
                       str(b["top10_hist_5y"]).replace("{", "").replace("}", ""), str(a["top10_hist_5y"]).replace("{", "").replace("}", "")])
    A(table(["zapytanie", "system", "średni rok top-10 przed", "po", "średni rok top-100 przed", "po", "rozkład lat top-10 przed (początek 5-latki: liczba)", "po"], rr))
    A("")
    for k in ("Q1", "Q2"):
        v = bo[k]
        rr = []
        for i in range(10):
            rr.append([i + 1, v["pg_before"][i]["year"], md_escape(short(v["pg_before"][i]["title"], 36)), v["pg_after"][i]["year"], md_escape(short(v["pg_after"][i]["title"], 36)),
                       v["solr_before"][i]["year"], md_escape(short(v["solr_before"][i]["title"], 36)), v["solr_after"][i]["year"], md_escape(short(v["solr_after"][i]["title"], 36))])
        A(f"**{k} — top-10 przed i po boostcie** (rok i tytuł):\n")
        A(table(["#", "PG przed", "tytuł", "PG po", "tytuł", "Solr przed", "tytuł", "Solr po", "tytuł"], rr))
        A("")
    A(f"""![Średni rok w top-10](../results/figures/boost_rok.png)

Wniosek: boost działa w obu systemach i przesuwa top-10 ku nowszym publikacjom (średni rok w top-10 rośnie o {n(min(v['year_stats'][e+'_after']['top10_mean_year']-v['year_stats'][e+'_before']['top10_mean_year'] for v in bo.values() for e in ('pg','solr')),1)}–{n(max(v['year_stats'][e+'_after']['top10_mean_year']-v['year_stats'][e+'_before']['top10_mean_year'] for v in bo.values() for e in ('pg','solr')),1)} lat zależnie od zapytania i systemu); po boostcie wspólnych dokumentów w top-10 jest
{bo['Q1']['overlap_top10_after']}/{bo['Q2']['overlap_top10_after']}/{bo['Q3']['overlap_top10_after']} (Q1/Q2/Q3). Boost jest zapisywany jako jedna deklaratywna funkcja w parametrach zapytania
(Solr), natomiast w SQL musi być wpisany w `ORDER BY` — przez to ranking trzeba policzyć dla wszystkich trafień, bez możliwości zatrzymania się wcześniej.
""")
    # 7.2 cursor
    A("### 7.2. Głębokie stronicowanie: `start/rows` a `cursorMark`\n")
    A(f"""Zapytanie szerokie `{pg['solr_q']}` ({n(pg['numFound'])} trafień, zbiór {pg['size']}%), sortowanie `score desc, id asc` (porządek całkowity — wymagany dla `cursorMark`),
strona = {pg['rows']} dokumentów. `cursorMark` jest bezstanowy: kursor uzyskany po przejściu do pozycji D można użyć wielokrotnie, więc mierzymy to samo żądanie powtórzone {pg['repeats']}×
(mediana); osobno podajemy koszt *dojścia* do głębokości D (suma kolejnych stron). SQL: `ORDER BY ts_rank_cd DESC, id LIMIT {pg['rows']} OFFSET D`.
Strony pobrane `start/rows` i `cursorMark` były identyczne we wszystkich pomiarach: {all(r['same_page_start_vs_cursor'] for r in pg['results'])}.
""")
    A(table(["głębokość D", "Solr start/rows [ms]", "Solr cursorMark [ms]", "dojście kursorem do D [s]", "SQL OFFSET [ms]"],
            [[n(r["depth"]), n(r["solr_start_rows"]["client_ms"]["median"], 1), n(r["solr_cursor"]["client_ms"]["median"], 1),
              n(r["solr_cursor"]["cumulative_walk_seconds_to_reach"], 2), n(r["sql_offset"]["client_ms"]["median"], 0)] for r in pg["results"]],
            ["---:", "---:", "---:", "---:", "---:"]))
    last = pg["results"][-1]
    A(f"""
![Głębokie stronicowanie](../results/figures/stronicowanie.png)

Czas `start/rows` rośnie z głębokością (Solr utrzymuje kolejkę priorytetową o rozmiarze `start+rows`): od {n(pg['results'][0]['solr_start_rows']['client_ms']['median'],0)} ms na początku do
{n(last['solr_start_rows']['client_ms']['median'],0)} ms przy D = {n(last['depth'])}; `cursorMark` pozostaje stały (~{n(last['solr_cursor']['client_ms']['median'],0)} ms), bo kursor niesie wartość sortowania ostatniego dokumentu
i serwer zaczyna od tego miejsca. W SQL `OFFSET` musi policzyć i posortować wszystkie trafienia (ranking) — {n(last['sql_offset']['client_ms']['median'],0)} ms przy D = {n(last['depth'])}
(i już ok. {n(pg['results'][0]['sql_offset']['client_ms']['median'],0)} ms dla pierwszej strony). Cena `cursorMark`: tylko do przodu, sekwencyjnie (nie ma skoku na dowolną stronę), a przejście całej listy kursorem kosztuje
{n(last['solr_cursor']['cumulative_walk_seconds_to_reach'],1)} s do D = {n(last['depth'])}.
""")
    # 7.3 sync
    A("### 7.3. Aktualizacja danych: zmiana i usunięcie w PostgreSQL, synchronizacja do Solra\n")
    A(f"""Mechanizm (`sql/03_sync.sql`, `lab3/sync.py`): trigger `BEFORE UPDATE` ustawia `updated_at`, trigger `AFTER DELETE` zapisuje id w tabeli `papers_100_deleted`;
tabela `sync_state` pamięta czas ostatniej synchronizacji. Skrypt synchronizujący wybiera wiersze z `updated_at` późniejszym niż ostatnia synchronizacja i wysyła je na `/update`
(dokument nadpisuje stary o tym samym `id`), usunięcia wysyła jako `delete by id`, robi jeden commit i zapisuje nowy czas synchronizacji.

Scenariusz (`python -m lab3.sync demo`, zbiór 100%): zmiana abstraktu w {len(sy['abstract_updated'])} rekordach (dopisane unikalne słowo-znacznik `xqzmarkerupdate`),
zmiana tytułu w {len(sy['title_updated'])} rekordach (`xqztitlemarker`) i usunięcie {len(sy['deleted'])} rekordów. Weryfikacja: (1) liczba dokumentów, (2) zapytania po znaczniku zwracają te same id,
(3) usunięte id nie występują w żadnym systemie, (4) zmienione dokumenty mają identyczny tytuł i abstrakt. Wynik:

| etap | liczba dokumentów PG = Solr | zapytania po znaczniku identyczne | usunięte nieobecne | zmienione dokumenty identyczne |
|---|:-:|:-:|:-:|:-:|
""" + "\n".join(
        f"| {lab} | {'tak' if e['detail']['total_count']['equal'] else '**nie**'} ({n(e['detail']['total_count']['pg'])} / {n(e['detail']['total_count']['solr'])}) | "
        f"{'tak' if e['detail']['marker_abstract']['equal'] and e['detail']['marker_title']['equal'] else '**nie**'} | "
        f"{('tak' if e['detail']['deleted_absent']['ok'] else '**nie**') if 'deleted_absent' in e['detail'] else '—'} | "
        f"{'tak' if e['detail']['changed_docs_identical']['ok'] else '**nie**'} |"
        for lab, e in (("po zmianach w PG, przed synchronizacją", next(x for x in sy['log'] if x['event'] == 'verify:before_sync')),
                       ("po synchronizacji", next(x for x in sy['log'] if x['event'] == 'verify:after_sync')),
                       ("po przywróceniu danych i ponownej synchronizacji", next(x for x in sy['log'] if x['event'] == 'verify:after_revert')))) + f"""

Przed synchronizacją systemy się rozjeżdżają (oczekiwane), po synchronizacji są zgodne: **{sy['consistent_after_sync']}**; po przywróceniu danych demo: **{sy['restored_after_revert']}**
(stan końcowy bazy i Solra = stan wyjściowy). Zsynchronizowano: {len(next(x for x in sy['log'] if x['event']=='sync' and x.get('deleted',0)>0)['deleted_ids'])} usunięć i
{next(x for x in sy['log'] if x['event']=='sync' and x.get('deleted',0)>0)['upserted']} aktualizacji. Pełny log z czasami: `results/sync_log.json`.
Ograniczenie: mechanizm jest *pull* (okresowy skrypt), nie transakcyjny — między zmianą w bazie a synchronizacją Solr widzi stare dane (eventual consistency).
""")
    # ------------------------------------------------------------------ 8. poziom 5.0
    A("## 8. Poziom 5.0: skalowanie i facety kontra GROUP BY\n")
    A("### 8.1. Skalowanie 10% → 50% → 100%\n")
    A("Osobne tabele i kolekcje (100 000, 500 000, 1 000 000 rekordów). Tryb count; mediana z 5; SQL — czas serwera (`EXPLAIN ANALYZE`), Solr — czas klienta (HTTP, wariant `cache=false`).\n")
    A("![Skalowanie: count](../results/figures/skalowanie_count.png)\n")
    rr = []
    for q in ("Q1", "Q2", "Q3"):
        for s in ("10", "50", "100"):
            rr.append([q, f"{s}%", n(m(s, q, "count", "LIKE")["result_count"]), n(sv(m(s, q, "count", "LIKE")), 0), n(sv(m(s, q, "count", "FTS")), 1),
                       n(sv(m(s, q, "count", "Solr")), 0), n(cl(m(s, q, "count", "Solr")), 1), n(cl(m(s, q, "count", "Solr+cache")), 1)])
    A(table(["zapytanie", "zbiór", "wyniki LIKE", "LIKE [ms]", "FTS [ms]", "Solr QTime [ms]", "Solr klient [ms]", "Solr klient, z cache [ms]"], rr,
            ["---", "---", "---:", "---:", "---:", "---:", "---:", "---:"]))
    A("\n![Skalowanie: top-10](../results/figures/skalowanie_top10.png)\n")
    rr = []
    for q in ("Q1", "Q2", "Q3"):
        for s in ("10", "50", "100"):
            rr.append([q, f"{s}%", n(sv(m(s, q, "top10", "FTS")), 1), n(sv(m(s, q, "top10", "Solr")), 0), n(cl(m(s, q, "top10", "Solr")), 1)])
    A(table(["zapytanie", "zbiór", "PG ts_rank_cd top-10 [ms]", "Solr QTime [ms]", "Solr klient [ms]"], rr, ["---", "---", "---:", "---:", "---:"]))
    like_g = sv(m("100", "Q1", "count", "LIKE")) / sv(m("10", "Q1", "count", "LIKE"))
    fts_g1 = sv(m("100", "Q1", "count", "FTS")) / sv(m("10", "Q1", "count", "FTS"))
    fts_g3 = sv(m("100", "Q3", "count", "FTS")) / sv(m("10", "Q3", "count", "FTS"))
    top1 = sv(m("100", "Q1", "top10", "FTS")) / sv(m("10", "Q1", "top10", "FTS"))
    A(f"""
**Wnioski ze skalowania.**

- `LIKE` rośnie z rozmiarem zbioru (10× więcej danych → {n(like_g,1)}× dłuższy czas dla Q1; mniej niż 10× — prawdopodobnie przez stały narzut i równoległy skan; nie badaliśmy tego osobno),
  ale już przy 100 tys. rekordów kosztuje ok. {n(sv(m('10','Q1','count','LIKE'))/1000,1)} s, a przy 1 mln ok. {n(sv(m('100','Q1','count','LIKE'))/1000,1)} s — niezależnie od zapytania, bo za każdym razem skanuje całą tabelę.
  Jako narzędzie interaktywne przestaje wystarczać już w okolicach 10^5 rekordów (>1 s), a przy 10^6 jest dziesiątki–setki razy wolniejszy od FTS.
- Koszt FTS z indeksem GIN zależy od **liczby trafień** (a ta rośnie z rozmiarem zbioru), a nie od skanowania całej tabeli: Q1 (dużo trafień, {n(m('100','Q1','count','FTS')['result_count'])}) — {n(fts_g1,1)}× więcej czasu przy 10× danych
  ({n(sv(m('10','Q1','count','FTS')),1)} → {n(sv(m('100','Q1','count','FTS')),1)} ms), Q3 (mało trafień) — {n(fts_g3,1)}× (wartości bezwzględne pozostają małe: {n(sv(m('100','Q3','count','FTS')),0)} ms przy 1 mln). Top-10 z rankingiem jest znacznie droższy niż samo zliczanie
  (Q1: {n(sv(m('100','Q1','top10','FTS')),0)} ms przy 100%, {n(top1,1)}× więcej niż przy 10%), bo `ts_rank_cd` musi policzyć wynik dla **wszystkich** trafień (odczyt i dekompresja `tsv` z TOAST) przed sortowaniem.
- Solr w trybie count utrzymuje czas niemal stały ({n(cl(m('10','Q1','count','Solr')),1)} ms przy 10% i {n(cl(m('100','Q1','count','Solr')),1)} ms przy 100% w czasie klienta dla Q1; dominuje narzut HTTP), a w trybie top-10 z rankingiem
  {n(sv(m('100','Q1','top10','Solr')),0)}–{n(sv(m('100','Q3','top10','Solr')),0)} ms serwera przy 100% — rzędy wielkości mniej niż PostgreSQL dla trafień masowych (Q1: {n(sv(m('100','Q1','top10','FTS')),0)} ms).
- **Punkt przecięcia:** dla zapytania o małej liczbie trafień (Q3) PostgreSQL FTS jest szybszy lub równy Solrowi w trybie count na zbiorach 10–50% (serwer {n(sv(m('10','Q3','count','FTS')),1)} ms, {n(sv(m('50','Q3','count','FTS')),1)} ms
  wobec klienta Solra {n(cl(m('10','Q3','count','Solr')),1)} / {n(cl(m('50','Q3','count','Solr')),1)} ms), więc dla małych zbiorów i rzadkich słów indeks w bazie w pełni wystarcza. Przewaga Solra rośnie z liczbą trafień i rozmiarem zbioru,
  a największa jest w rankingu (top-10).
- Reguła praktyczna z naszych liczb: `LIKE '%…%'` — tylko do ~10^4–10^5 rekordów lub jednorazowo; FTS w PostgreSQL — do ~10^6 rekordów, gdy zapytania są selektywne lub wystarczy liczba/filtry, a ranking obejmuje
  niewiele trafień; Solr — gdy potrzebny jest szybki ranking dużych zbiorów trafień, facety, podświetlanie i stronicowanie.
""")
    # 8.2 facets
    A("### 8.2. Facety Solra a GROUP BY / GROUPING SETS\n")
    r0 = next(x for x in fv["results"] if x["size"] == "100" and x["case"] == "Q1")
    A(f"""Jedno zapytanie Solra: `facet=true&facet.field=primary_category&facet.field=archive&facet.range=year&facet.range.start={fv['range']['start']}&facet.range.end={fv['range']['end']}&facet.range.gap={fv['range']['gap']}&facet.mincount=1&facet.limit=-1&rows=0`
(przykładowy pełny URL: `results/facets_vs_groupby.json`, np. dla Q1: `{r0['solr_url'][:160]}…`). Odpowiedniki SQL: trzy osobne `GROUP BY` (kategoria, archiwum, przedział lat
`{fv['range']['start']} + ((year - {fv['range']['start']}) / {fv['range']['gap']}) * {fv['range']['gap']}`) oraz jedno zapytanie `GROUP BY GROUPING SETS ((primary_category),(archive),(bucket))`.
Przypadki: `ALL` (cały zbiór), `STRUCT` (filtr `archive=cs AND year>=2015` — identyczny zbiór w obu systemach), `Q1`–`Q3` (zbiory z zapytań tekstowych). Zbiór 100%, mediana z 5:
""")
    rr = []
    for r in fv["results"]:
        if r["size"] != "100":
            continue
        c = r["comparison"]
        same = all(v["identical"] for v in c.values())
        diff = max(v["max_abs_diff"] for v in c.values())
        rr.append([r["case"], n(r["solr_numFound"]), n(r["solr_qtime_ms"]["median"], 0), n(r["solr_client_ms"]["median"], 1),
                   n(r["sql_separate_sum_exec_ms"], 1), n(r["sql_grouping_sets"]["exec_ms"]["median"], 1),
                   "tak" if same else f"nie (maks. różnica {diff})", "tak" if r["grouping_sets_equals_separate"] else "nie"])
    A(table(["przypadek", "dopasowanych dok.", "Solr QTime [ms]", "Solr klient [ms]", "SQL 3×GROUP BY [ms]", "SQL GROUPING SETS [ms]", "liczności identyczne (Solr = SQL)", "GROUPING SETS = 3×GROUP BY"], rr,
            ["---", "---:", "---:", "---:", "---:", "---:", "---", "---"]))
    allr = next(x for x in fv["results"] if x["size"] == "100" and x["case"] == "ALL")
    A(f"""
![Facety kontra GROUP BY](../results/figures/facety_vs_groupby.png)

- **Poprawność.** Dla zbiorów wyznaczonych warunkami strukturalnymi (`ALL`, `STRUCT`) liczności z Solra i z SQL są **identyczne** we wszystkich trzech agregacjach; w `ALL` suma przedziałów lat to
  {n(allr['comparison']['year']['sum_solr'])} z {n(allr['solr_numFound'])}, bo {n(allr['solr_numFound'] - allr['comparison']['year']['sum_solr'])} rekordów jest sprzed {fv['range']['start']} roku. Dla zapytań tekstowych liczności różnią się o kilka–kilkadziesiąt,
  dokładnie z powodu różnic w zbiorze trafień (p. 5.2) — nie z powodu samych facetów. Wariant `GROUPING SETS` daje wyniki identyczne z trzema osobnymi `GROUP BY`.
- **Czas.** Facety Solra liczą się na strukturach `docValues` w jednym żądaniu: {n(allr['solr_client_ms']['median'],0)} ms (klient) dla całego zbioru ({n(allr['solr_numFound'])} dok.)
  wobec {n(allr['sql_separate_sum_exec_ms'],0)} ms (suma trzech `GROUP BY`) i {n(allr['sql_grouping_sets']['exec_ms']['median'],0)} ms (`GROUPING SETS`) w PostgreSQL. Stosunek najlepszego czasu SQL do czasu klienta Solra:
  {", ".join(f"{r['case']} — {n(min(r['sql_separate_sum_exec_ms'], r['sql_grouping_sets']['exec_ms']['median'])/r['solr_client_ms']['median'],1)}×" for r in fv['results'] if r['size']=='100')}.
  Solr jest szybszy we wszystkich przypadkach, a przewaga maleje, gdy zbiór trafień jest mały (Q3 — indeks GIN ogranicza SQL do kilku tysięcy wierszy). Wariant `GROUPING SETS` względem trzech osobnych `GROUP BY`:
  {", ".join(f"{r['case']}: {'szybszy' if r['sql_grouping_sets']['exec_ms']['median'] < r['sql_separate_sum_exec_ms'] else 'wolniejszy'} ({n(r['sql_grouping_sets']['exec_ms']['median'],0)} vs {n(r['sql_separate_sum_exec_ms'],0)} ms)" for r in fv['results'] if r['size']=='100')}
  — zależy od selektywności i planu. Zaleta Solra poza czasem: facety są częścią zwykłego zapytania (`fq`, ranking i podświetlanie w tym samym żądaniu), w SQL to osobne zapytania agregujące.
""")
    # ------------------------------------------------------------------ 9. wnioski
    A(f"""## 9. Wnioski: kiedy indeks w bazie wystarcza, a kiedy sięgnąć po Solra

Wnioski opieramy na liczbach z pomiarów (zbiór do 1 mln rekordów, abstrakty ≈ {n(d100['abstract_len_mean'])} znaków, jeden węzeł, 12 wątków, 2 GB sterty Solra):

1. **LIKE '%…%' nie skaluje się.** Zawsze skanuje całą tabelę: {n(sv(m('10','Q1','count','LIKE'))/1000,1)} s (100 tys.) → {n(sv(m('100','Q1','count','LIKE'))/1000,1)} s (1 mln), przy 1 mln {n(min(sv(m('100',q,'count','LIKE'))/sv(m('100',q,'count','FTS')) for q in ('Q1','Q2','Q3')),0)}–{n(max(sv(m('100',q,'count','LIKE'))/sv(m('100',q,'count','FTS')) for q in ('Q1','Q2','Q3')),0)}× wolniej od FTS
   i nie rozumie fleksji (Q1: {n(rows[0]['like']['result_count'])} wyników zamiast {n(rows[0]['fts']['result_count'])}), granic wyrazów ani frazy.
2. **Indeks pełnotekstowy w PostgreSQL wystarcza,** gdy zbiór ma do ok. 10^6 dokumentów, zapytania są selektywne (Q3: {n(sv(m('100','Q3','count','FTS')),0)} ms przy 1 mln) albo potrzebne są tylko liczby/filtry,
   gdy zależy nam na jednym systemie (transakcje, `JOIN`, jedno źródło prawdy, brak synchronizacji) i gdy wystarczy prosty ranking. Koszt dodatkowy to rozmiar (tabela z `tsv`: {mib(pgt['papers_100']['table_bytes_with_toast'])} MiB, GIN {mib(pgt['papers_100']['gin_bytes'])} MiB).
3. **Warto sięgnąć po Solra,** gdy: (a) zapytania mają **wiele trafień i potrzebny jest ranking** — top-10 dla Q1 przy 1 mln: PostgreSQL {n(sv(m('100','Q1','top10','FTS')),0)} ms,
   Solr {n(sv(m('100','Q1','top10','Solr')),0)} ms (a przy cache wyników ułamek ms); (b) potrzebne są **facety, podświetlanie, boosty, `cursorMark`** — w Solrze to parametry zapytania,
   w SQL osobne, kosztowne konstrukcje (np. głębokie strony: {n(last['sql_offset']['client_ms']['median'],0)} ms `OFFSET` kontra {n(last['solr_cursor']['client_ms']['median'],0)} ms `cursorMark`);
   (c) liczba dokumentów lub zapytań rośnie (czas Solra w trybie count prawie nie zależy od rozmiaru zbioru); (d) zimny start jest dla użytkownika odczuwalny —
   pierwsze FTS Q1 po restarcie trwało {n(next(x for x in cold['results'] if x['query_key']=='Q1' and x['method']=='FTS count')['first_run_client_ms']/1000,1)} s (Solr {n(next(x for x in cold['results'] if x['query_key']=='Q1' and x['method']=='Solr count')['first_run_client_ms'],0)} ms).
4. **Cena Solra:** drugi system do utrzymania, **spójność ewentualna** (synchronizacja z bazą — p. 7.3), osobny schemat i analiza tekstu (różnice w tokenizacji dają inne wyniki w skrajnych przypadkach, p. 5.2),
   mniejsze ale niezerowe zużycie dysku i pamięci (indeks {mib(srt['papers_100']['index_bytes_settled'])} MiB, sterta 2 GB), czas ładowania i indeksowania zbioru 100%: Solr {n(srt['papers_100']['total_seconds'],0)} s wobec {n(sum(pgt['papers_100'][k] for k in ('copy_seconds','gin_seconds')),0)} s w PostgreSQL (COPY z liczeniem `tsv` + GIN).
5. **Rankingi się różnią:** wspólnych dokumentów w top-10 `ts_rank_cd` i BM25 jest w naszych zapytaniach {l4['Q1']['common_top10_count']}/{l4['Q2']['common_top10_count']}/{l4['Q3']['common_top10_count']} (Q1/Q2/Q3) — wybór metody rankingu jest decyzją produktową; nie oceniano trafności przez człowieka, więc nie rozstrzygamy, który ranking jest „lepszy”;
   oba systemy pozwalają wprowadzić wagi pól i boost.

### Ograniczenia

- Pojedyncza maszyna (Docker Desktop, współdzielone zasoby hosta), pojedynczy węzeł Solra (1 shard, 1 replika); wyniki dotyczą tego sprzętu.
- Czasy klienta Solra zawierają narzut HTTP/JSON; `QTime` ma rozdzielczość 1 ms (wartości `0` oznaczają < 1 ms). Czasy SQL (*Execution Time*) nie zawierają przesyłu wyniku.
- Zimny start: dane po restarcie i `drop_caches` w VM Dockera; nie jest to pomiar „zimnego dysku fizycznego”.
- Zbiór ma jeden język (angielski) i abstrakty ≈ 1 kB; dla innych języków i dłuższych dokumentów proporcje mogą być inne.
- `ts_rank_cd` i BM25 porównaliśmy jakościowo (liczba wspólnych dokumentów), bez oceny trafności przez człowieka.
""")
    return "\n".join(o)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authors", nargs="+", default=["<Imię Nazwisko>", "<Imię Nazwisko>"])
    args = ap.parse_args()
    md = build(args.authors)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "sprawozdanie.md").write_text(md, encoding="utf-8")
    print("Zapisano docs/sprawozdanie.md")

    from lab3.oral import main as oral_main
    oral_main()

    # README: wstaw tabelę wyników poziomu 3.0 między znaczniki
    l3 = J("level3.json")
    rows = l3["rows"]
    t = table(["zapytanie", "wyniki LIKE", "wyniki FTS (SQL)", "numFound Solr", "czas LIKE [ms]", "czas FTS [ms]", "QTime Solr [ms]", "QTime Solr, cache=false [ms]"],
              [[f"{r['key']}: {r['title']}", n(r["like"]["result_count"]), n(r["fts"]["result_count"]), n(r["solr"]["result_count"]),
                n(r["like"]["exec_ms"]["median"], 1), n(r["fts"]["exec_ms"]["median"], 1), n(r["solr"]["qtime_ms"]["median"], 0),
                n(r["solr_nocache"]["qtime_ms"]["median"], 0)] for r in rows], ["---", "---:", "---:", "---:", "---:", "---:", "---:", "---:"])
    rd = ROOT / "README.md"
    txt = rd.read_text(encoding="utf-8")
    block = f"<!-- TABELA30:START -->\n{t}\n\nZbiór: `{l3['table']}` ({n(J('dataset_stats.json')['datasets']['papers_100']['records'])} rekordów), mediana z 5 uruchomień po rozgrzewce; czas SQL z `EXPLAIN (ANALYZE, BUFFERS)`.\n<!-- TABELA30:END -->"
    if "<!-- TABELA30:START -->" in txt:
        txt = re.sub(r"<!-- TABELA30:START -->.*?<!-- TABELA30:END -->", lambda _: block, txt, flags=re.S)
        rd.write_text(txt, encoding="utf-8")
        print("Zaktualizowano tabelę w README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
