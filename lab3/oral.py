"""Etap 8: generuje docs/odpowiedz_ustna.md — ściągę do odpowiedzi ustnej (liczby z results/).

Uruchomienie:  python -m lab3.oral      (wywoływane też przez python -m lab3.report)
"""
import sys

from lab3.config import ROOT
from lab3.report import J, mib, n


def build() -> str:
    ds = J("dataset_stats.json")["datasets"]["papers_100"]
    lpg, lsr = J("load_pg.json"), J("load_solr.json")
    pgt = {t["table"]: t for t in lpg["tables"]}
    srt = {c["collection"]: c for c in lsr["collections"]}
    bm = J("benchmark.json")["measurements"]
    l3 = {r["key"]: r for r in J("level3.json")["rows"]}
    d3 = J("level3_diffs.json")["diffs"]
    l4 = J("level4.json")["queries"]
    bo = J("level4_boost.json")["queries"]
    pg = J("paging.json")["results"]
    fv = {r["case"]: r for r in J("facets_vs_groupby.json")["results"] if r["size"] == "100"}
    cold = {(x["query_key"], x["method"]): x["first_run_client_ms"] for x in J("cold.json")["results"]}
    sy = J("sync_log.json")

    def m(size, q, mode, meth):
        return next(x for x in bm if x["size"] == size and x["query_key"] == q and x["mode"] == mode and x["method"] == meth)

    def sv(x):
        return x["exec_ms"]["median"] if "exec_ms" in x else x["qtime_ms"]["median"]

    def cl(x):
        return x["client_ms"]["median"]

    qa = []

    def Q(q, a):
        qa.append((q, a))

    Q("Czym jest indeks odwrócony i jak działa wyszukiwanie z jego użyciem?",
      "Odwzorowanie *termin → lista dokumentów* (postings; opcjonalnie pozycje, częstości). Zapytanie sprowadza się do pobrania list dla terminów i operacji na nich "
      "(AND = przecięcie, OR = suma, NOT = różnica), bez czytania tekstów. U nas: GIN w PostgreSQL (indeks na `tsv`) i indeks Lucene w Solrze. "
      f"Dlatego FTS Q1 ({n(m('100','Q1','count','FTS')['result_count'])} trafień) kosztuje {n(sv(m('100','Q1','count','FTS')),0)} ms, a `LIKE` — {n(sv(m('100','Q1','count','LIKE')),0)} ms.")
    Q("Co to jest analiza tekstu i jak wygląda łańcuch `text_en`?",
      "Przekształcenie tekstu w tokeny przy indeksowaniu i zapytaniu (tym samym łańcuchem, by się spotkały): tokenizer `standard` → stoplista → `lowercase` → `englishPossessive` → "
      "`keywordMarker` → `porterStem`; w zapytaniu dodatkowo `synonymGraph`. Dzięki stemmingowi `simulated/simulations/simulating` → `simul`.")
    Q("Czym różni się analiza w PostgreSQL (`english`) od `text_en` w Solrze?",
      "Ta sama idea, inne komponenty: PostgreSQL ma parser rozpoznający typy tokenów (URL, plik, host, słowo z myślnikiem), Snowball (Porter2) i swoją stoplistę; Solr — tokenizer UAX#29, "
      f"klasyczny Porter, stoplistę Lucene. Skutek: różnice rzędu dziesiątek dokumentów (Q1: {d3['Q1']['fts_only']} tylko w SQL, {d3['Q1']['solr_only']} tylko w Solrze), np. `simulation/data`, URL-e, `local_qasm_simulator`.")
    Q("Dlaczego `LIKE '%słowo%'` nie skaluje się?",
      f"Wiodący `%` uniemożliwia użycie indeksu B-tree — zawsze skan całej tabeli (u nas *Parallel Seq Scan*; nie zakładaliśmy `gin_trgm_ops`). Czas ~liniowy w rozmiarze: Q1 {n(sv(m('10','Q1','count','LIKE')),0)} ms (100 tys.), "
      f"{n(sv(m('50','Q1','count','LIKE')),0)} ms (500 tys.), {n(sv(m('100','Q1','count','LIKE')),0)} ms (1 mln) — niezależnie od liczby trafień; dodatkowo tabela ({mib(pgt['papers_100']['table_bytes_with_toast'])} MiB) nie mieści się w `shared_buffers`.")
    Q("Co znajduje `LIKE`, a czego nie — i odwrotnie dla FTS?",
      f"LIKE: podciągi (`resimulate`, `supercluster`), nie zna fleksji (nie znajdzie `simulation` po `simulate`), Q1: {n(l3['Q1']['like']['result_count'])} wyników wobec {n(l3['Q1']['fts']['result_count'])} w FTS. "
      "FTS znajduje formy po stemmingu, ale nie podciągi i nie literówki.")
    Q("Jak działa tsvector + GIN w PostgreSQL? Po co `setweight`?",
      f"`tsv` = leksemy z pozycjami i wagami (A dla tytułu, B dla abstraktu), kolumna `GENERATED … STORED` (średnio {n(pgt['papers_100']['avg_tsv_bytes'])} B/wiersz); GIN = indeks odwrócony po leksemach "
      f"({mib(pgt['papers_100']['gin_bytes'])} MiB dla 1 mln). Wagi wpływają na `ts_rank_cd` (tytuł liczy się bardziej).")
    Q("`to_tsquery`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery` — czym się różnią?",
      "`to_tsquery` — pełna składnia (`&`, `|`, `!`, `<->`); `plainto_tsquery` — słowa połączone AND; `phraseto_tsquery` — słowa obok siebie w kolejności (`<->`); "
      "`websearch_to_tsquery` — składnia jak w wyszukiwarce (cudzysłów, `or`, `-`). U nas Q1 plainto, Q2 phraseto, Q3 to_tsquery.")
    Q("BM25 a `ts_rank_cd` — czym się różnią i dlaczego top-10 się różni?",
      f"BM25 (Solr): IDF + nasycenie częstości + normalizacja długości pola. `ts_rank_cd`: gęstość i bliskość wystąpień, domyślnie bez normalizacji długości. "
      f"Wspólnych dokumentów w top-10: {l4['Q1']['common_top10_count']}/{l4['Q2']['common_top10_count']}/{l4['Q3']['common_top10_count']} (Q1/Q2/Q3), w top-100: {l4['Q1']['common_top100_count']}/{l4['Q2']['common_top100_count']}/{l4['Q3']['common_top100_count']}; "
      f"z normalizacją długości (flaga 2) top-100: {l4['Q1']['common_top100_count_pg_norm2']}/{l4['Q2']['common_top100_count_pg_norm2']}/{l4['Q3']['common_top100_count_pg_norm2']}.")
    Q("Co oznaczają flagi pola w Solrze: indexed, stored, docValues, multiValued?",
      "`indexed` — pole przeszukiwalne (indeks odwrócony); `stored` — oryginalna wartość do zwrócenia/podświetlenia; `docValues` — kolumnowa struktura do sortowania, facetów, funkcji (nie dla pól analizowanych); "
      "`multiValued` — wiele wartości (u nas `categories`, `text_all`). Przykład: `text_all` ma `stored=false` (nie wyświetlamy), a `year` ma docValues (facet.range, boost, sort).")
    Q("Do czego `copyField` i `text_all`?",
      "Kopiuje `title` i `abstract` do jednego pola, żeby zapytanie 3.0 (`q=text_all:…`) przeszukiwało oba bez wymieniania pól. Nie przechowujemy go (`stored=false`). "
      "W eDisMax zamiast tego używamy `qf=title^3 abstract`, co pozwala nadać wagi.")
    Q("Jaka jest różnica między `q` a `fq`?",
      "`q` — zapytanie liczące trafność (score); `fq` — filtr bez wpływu na score, cache'owany w `filterCache` (dobry do powtarzalnych ograniczeń, np. `archive:astro-ph`, `year:[2010 TO 2020]`). "
      f"W wariancie Q1+fq Solr zwrócił numFound={n(l3['Q1+fq']['solr']['result_count'])}.")
    Q("Co to eDisMax i po co `qf`, `pf`, `boost`?",
      "Parser zapytań dla użytkowników: wiele pól z wagami (`qf=title^3 abstract`), premia za frazę (`pf`), tolerancyjny na błędy składni, obsługuje AND/OR/NOT; `boost` — mnożnik wyniku funkcją. "
      "U nas Q1–Q3 w eDisMax, `pf` dla frazy, `boost=exp(mul(0.08,sub(year,2025)))` w rozszerzeniu.")
    Q("Facety kontra `GROUP BY` — co jest podobne, co inne?",
      f"Facet = liczności wartości pola dla zbioru trafień, liczone na docValues w jednym żądaniu razem z wyszukiwaniem; `GROUP BY` to osobne zapytanie. Dla zbioru całego ({n(fv['ALL']['solr_numFound'])} dok.): Solr {n(fv['ALL']['solr_client_ms']['median'],0)} ms "
      f"vs SQL {n(fv['ALL']['sql_separate_sum_exec_ms'],0)} ms (3×GROUP BY) / {n(fv['ALL']['sql_grouping_sets']['exec_ms']['median'],0)} ms (GROUPING SETS). Liczności identyczne dla filtru strukturalnego; dla zapytań tekstowych "
      "różnią się o kilkadziesiąt przez tokenizację.")
    Q("Co to `facet.range` i jak go użyliśmy?",
      f"Facet zakresowy po polu liczbowym: `facet.range=year&facet.range.start={J('facets_vs_groupby.json')['range']['start']}&facet.range.end={J('facets_vs_groupby.json')['range']['end']}&facet.range.gap={J('facets_vs_groupby.json')['range']['gap']}` — przedziały 5-letnie; "
      "odpowiednik w SQL: wyrażenie `start + ((year-start)/gap)*gap` w `GROUP BY`.")
    Q("Czym jest commit w Solrze i dlaczego jeden na końcu?",
      f"Commit czyni zmiany widocznymi (otwiera nowy searcher) i utrwala segmenty. Częste commity (np. `autoSoftCommit` co 3 s w `_default`) spowalniają ładowanie, więc wyłączyliśmy auto-commity i robimy jeden na końcu: "
      f"100%: wysyłanie {n(srt['papers_100']['send_seconds'],0)} s + commit {n(srt['papers_100']['commit_seconds'],1)} s.")
    Q("Ile trwało ładowanie i indeksowanie w obu systemach?",
      f"100%: PostgreSQL COPY {n(pgt['papers_100']['copy_seconds'],0)} s (z liczeniem `tsv`) + GIN {n(pgt['papers_100']['gin_seconds'],0)} s; Solr {n(srt['papers_100']['total_seconds'],0)} s razem. "
      f"Rozmiar: PG tabela {mib(pgt['papers_100']['table_bytes_with_toast'])} MiB + indeksy {mib(pgt['papers_100']['indexes_bytes'])} MiB; Solr {mib(srt['papers_100']['index_bytes_settled'])} MiB po scaleniu segmentów.")
    Q("Dlaczego w pomiarach Solra mierzycie z `cache=false`?",
      f"Powtórzone zapytanie wraca z `queryResultCache` (QTime ≈ 0 ms) — to nie mierzy dopasowania ani rankingu. Q1 top-10 przy 100%: z cache {n(sv(m('100','Q1','top10','Solr+cache')),0)} ms, bez cache {n(sv(m('100','Q1','top10','Solr')),0)} ms (QTime), "
      f"PostgreSQL {n(sv(m('100','Q1','top10','FTS')),0)} ms.")
    Q("Jak mierzyliście czas i co to jest rozgrzany/zimny cache?",
      f"1 rozgrzewka + 5 pomiarów, mediana; SQL: `EXPLAIN (ANALYZE, BUFFERS)` i czas klienta, Solr: QTime i czas klienta. Zimny start: restart kontenerów + `drop_caches` w VM Dockera. "
      f"Q1 count po restarcie: PG {n(cold[('Q1','FTS count')]/1000,1)} s (rozgrzany {n(sv(m('100','Q1','count','FTS')),0)} ms), Solr {n(cold[('Q1','Solr count')],0)} ms.")
    Q("Co pokazało skalowanie 10% → 100%?",
      f"LIKE rośnie ({n(sv(m('10','Q1','count','LIKE')),0)} → {n(sv(m('100','Q1','count','LIKE')),0)} ms), FTS skaluje się z liczbą trafień ({n(sv(m('10','Q1','count','FTS')),0)} → {n(sv(m('100','Q1','count','FTS')),0)} ms; "
      f"Q3: {n(sv(m('10','Q3','count','FTS')),1)} → {n(sv(m('100','Q3','count','FTS')),0)} ms), Solr w count prawie stały ({n(cl(m('10','Q1','count','Solr')),1)} → {n(cl(m('100','Q1','count','Solr')),1)} ms klienta). "
      f"Top-10 z rankingiem w PG: Q1 {n(sv(m('10','Q1','top10','FTS')),0)} → {n(sv(m('100','Q1','top10','FTS')),0)} ms; Solr {n(sv(m('10','Q1','top10','Solr')),0)} → {n(sv(m('100','Q1','top10','Solr')),0)} ms.")
    Q("Kiedy indeks w bazie wystarcza, a kiedy sięgnąć po Solra?",
      "Baza: do ~10^6 rekordów, zapytania selektywne, jedno źródło prawdy, bez potrzeby facetów/podświetlania/zaawansowanego rankingu. Solr: ranking dużych zbiorów trafień, facety, hl, boosty, stronicowanie, "
      f"wyższe obciążenie. Koszt Solra: drugi system, spójność ewentualna (sync), osobny schemat. Liczby: Q1 top-10 PG {n(sv(m('100','Q1','top10','FTS')),0)} ms vs Solr {n(sv(m('100','Q1','top10','Solr')),0)} ms.")
    Q("Co to głębokie stronicowanie i czemu `start/rows` jest wolne?",
      f"Dla `start=D` serwer musi utrzymać kolejkę priorytetową `D+rows` dokumentów i odrzucić pierwsze D, więc koszt rośnie z D. Przy D=500 000: start/rows {n(pg[-1]['solr_start_rows']['client_ms']['median'],0)} ms, "
      f"cursorMark {n(pg[-1]['solr_cursor']['client_ms']['median'],0)} ms, SQL OFFSET {n(pg[-1]['sql_offset']['client_ms']['median'],0)} ms.")
    Q("Jak działa `cursorMark` i jakie ma ograniczenia?",
      "Kursor to zakodowana wartość sortowania ostatniego dokumentu; kolejne żądanie zaczyna od niej (`sort` musi zawierać `uniqueKey`, u nas `score desc, id asc`). Stały koszt strony, bezstanowy, stabilny przy zmianach. "
      "Ograniczenia: tylko do przodu, brak skoku do dowolnej strony, `start` nie może być użyty razem z kursorem.")
    Q("Jak zsynchronizowaliście zmiany z PostgreSQL do Solra?",
      f"Trigger BEFORE UPDATE ustawia `updated_at`, trigger AFTER DELETE zapisuje id w tabeli usunięć; skrypt wysyła zmienione wiersze na `/update` (nadpisanie po id) i usunięcia jako delete by id, commit, zapamiętuje czas. "
      f"Demo: {len(sy['abstract_updated'])} zmian abstraktu, {len(sy['title_updated'])} tytułu, {len(sy['deleted'])} usunięć; po synchronizacji zgodność = {sy['consistent_after_sync']}.")
    Q("Jakie są wady takiej synchronizacji?",
      "Pull (okresowa), nie transakcyjna — okno niespójności między zmianą w bazie a sync; usunięcia wymagają osobnego śledzenia; dla bardzo dużej liczby zmian lepsze CDC (np. Debezium) lub kolejka.")
    Q("Jak działa boost rokiem i co zmienił w top-10?",
      f"Mnożnik `exp(0,08·(year−2025))` w Solrze (`boost=`) i w SQL (`ts_rank_cd * exp(…)`). Średni rok top-10 (PG przed→po): Q1 {n(bo['Q1']['year_stats']['pg_before']['top10_mean_year'],1)}→{n(bo['Q1']['year_stats']['pg_after']['top10_mean_year'],1)}, "
      f"Solr: {n(bo['Q1']['year_stats']['solr_before']['top10_mean_year'],1)}→{n(bo['Q1']['year_stats']['solr_after']['top10_mean_year'],1)}.")
    Q("Czy dane były powielane? Jak wpływa to na wyniki?",
      f"Nie — wzięliśmy {n(ds['records'])} rzeczywistych rekordów z arXiv (ponad 3 mln dostępnych), więc nie ma duplikatów w top-10 ani zawyżonych liczności facetów. "
      f"(Duplikaty `id` w źródle — {J('dataset_stats.json')['duplicate_ids_dropped']} — usunęliśmy przy przygotowaniu danych.)")
    Q("Dlaczego Solr działa w trybie SolrCloud i co to zmieniło w projekcie?",
      "Obraz `solr:10` startuje domyślnie w SolrCloud z wbudowanym ZooKeeperem. Konsekwencja: schemat i konfiguracja leżą w configsecie w ZK współdzielonym przez kolekcje, więc każda kolekcja (`papers_10/50/100`) ma własny configset (kopia `_default`); "
      "kolekcje tworzymy Collections API, schemat Schema API, config Config API.")
    Q("Dlaczego `update.autoCreateFields=false`?",
      "Wyłącza schemaless: nieznane pole w dokumencie powoduje błąd zamiast cichego utworzenia pola o domyślnym typie. Sprawdziliśmy: wysłanie dokumentu z nieistniejącym polem zwraca `unknown field`.")
    Q("Jakie są ograniczenia Waszych pomiarów?",
      "Jedna maszyna (Docker Desktop, 12 wątków, 2 GB sterty Solra), jeden węzeł; QTime ma rozdzielczość 1 ms; czas klienta Solra zawiera HTTP; porównanie rankingów tylko ilościowe (wspólne dokumenty), bez oceny trafności przez człowieka; "
      "„zimny” start to restart + drop_caches w VM, nie zimny dysk fizyczny.")

    out = ["# Ściąga do odpowiedzi ustnej — Lab 3 PJN (poziom 5.0)", "",
           "Odpowiedzi odwołują się do naszego projektu i liczb z `results/` (plik generowany: `python -m lab3.oral`). "
           f"Zbiór: {n(ds['records'])} rekordów arXiv (abstrakt średnio {n(ds['abstract_len_mean'])} znaków), PostgreSQL 17 vs Solr 10.", ""]
    for i, (q, a) in enumerate(qa, 1):
        out += [f"## {i}. {q}", "", a, ""]
    return "\n".join(out)


def main() -> int:
    (ROOT / "docs" / "odpowiedz_ustna.md").write_text(build(), encoding="utf-8")
    print("Zapisano docs/odpowiedz_ustna.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
