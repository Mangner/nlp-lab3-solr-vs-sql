# Ściąga do odpowiedzi ustnej — Lab 3 PJN (poziom 4.0)

Odpowiedzi odwołują się do naszego projektu i liczb z `results/` (plik generowany: `python -m lab3.oral`). Zbiór: 1 000 000 rekordów arXiv (abstrakt średnio 1 048 znaków), PostgreSQL 17 vs Solr 10.

## 1. Czym jest indeks odwrócony i jak działa wyszukiwanie z jego użyciem?

Odwzorowanie *termin → lista dokumentów* (postings; opcjonalnie pozycje, częstości). Zapytanie sprowadza się do pobrania list dla terminów i operacji na nich (AND = przecięcie, OR = suma, NOT = różnica), bez czytania tekstów. U nas: GIN w PostgreSQL (indeks na `tsv`) i indeks Lucene w Solrze. Dlatego FTS Q1 (119 222 trafień) kosztuje 113 ms, a `LIKE` — 4 632 ms.

## 2. Co to jest analiza tekstu i jak wygląda łańcuch `text_en`?

Przekształcenie tekstu w tokeny przy indeksowaniu i zapytaniu (tym samym łańcuchem, by się spotkały): tokenizer `standard` → stoplista → `lowercase` → `englishPossessive` → `keywordMarker` → `porterStem`; w zapytaniu dodatkowo `synonymGraph`. Dzięki stemmingowi `simulated/simulations/simulating` → `simul`.

## 3. Czym różni się analiza w PostgreSQL (`english`) od `text_en` w Solrze?

Ta sama idea, inne komponenty: PostgreSQL ma parser rozpoznający typy tokenów (URL, plik, host, słowo z myślnikiem), Snowball (Porter2) i swoją stoplistę; Solr — tokenizer UAX#29, klasyczny Porter, stoplistę Lucene. Skutek: różnice rzędu dziesiątek dokumentów (Q1: 2 tylko w SQL, 35 tylko w Solrze), np. `simulation/data`, URL-e, `local_qasm_simulator`.

## 4. Dlaczego `LIKE '%słowo%'` jest wolny?

Wiodący `%` uniemożliwia użycie indeksu B-tree — zawsze skan całej tabeli (u nas *Parallel Seq Scan*; nie zakładaliśmy `gin_trgm_ops`). Przy 1 mln rekordów: Q1 4 632 ms, Q2 4 579 ms, Q3 4 817 ms — niezależnie od liczby trafień; dodatkowo tabela (2 438 MiB) nie mieści się w `shared_buffers`.

## 5. Co znajduje `LIKE`, a czego nie — i odwrotnie dla FTS?

LIKE: podciągi (`resimulate`, `supercluster`), nie zna fleksji (nie znajdzie `simulation` po `simulate`), Q1: 24 333 wyników wobec 119 222 w FTS. FTS znajduje formy po stemmingu, ale nie podciągi i nie literówki.

## 6. Jak działa tsvector + GIN w PostgreSQL? Po co `setweight`?

`tsv` = leksemy z pozycjami i wagami (A dla tytułu, B dla abstraktu), kolumna `GENERATED … STORED` (średnio 1 188 B/wiersz); GIN = indeks odwrócony po leksemach (301 MiB dla 1 mln). Wagi wpływają na `ts_rank_cd` (tytuł liczy się bardziej).

## 7. `to_tsquery`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery` — czym się różnią?

`to_tsquery` — pełna składnia (`&`, `|`, `!`, `<->`); `plainto_tsquery` — słowa połączone AND; `phraseto_tsquery` — słowa obok siebie w kolejności (`<->`); `websearch_to_tsquery` — składnia jak w wyszukiwarce (cudzysłów, `or`, `-`). U nas Q1 plainto, Q2 phraseto, Q3 to_tsquery.

## 8. BM25 a `ts_rank_cd` — czym się różnią i dlaczego top-10 się różni?

BM25 (Solr): IDF + nasycenie częstości + normalizacja długości pola. `ts_rank_cd`: gęstość i bliskość wystąpień, domyślnie bez normalizacji długości. Wspólnych dokumentów w top-10: 0/0/0 (Q1/Q2/Q3), w top-100: 7/5/9; z normalizacją długości (flaga 2) top-100: 14/16/11.

## 9. Co oznaczają flagi pola w Solrze: indexed, stored, docValues, multiValued?

`indexed` — pole przeszukiwalne (indeks odwrócony); `stored` — oryginalna wartość do zwrócenia/podświetlenia; `docValues` — kolumnowa struktura do sortowania, facetów, funkcji (nie dla pól analizowanych); `multiValued` — wiele wartości (u nas `categories`, `text_all`). Przykład: `text_all` ma `stored=false` (nie wyświetlamy), a `year` ma docValues (boost, sort).

## 10. Do czego `copyField` i `text_all`?

Kopiuje `title` i `abstract` do jednego pola, żeby zapytanie 3.0 (`q=text_all:…`) przeszukiwało oba bez wymieniania pól. Nie przechowujemy go (`stored=false`). W eDisMax zamiast tego używamy `qf=title^3 abstract`, co pozwala nadać wagi.

## 11. Jaka jest różnica między `q` a `fq`?

`q` — zapytanie liczące trafność (score); `fq` — filtr bez wpływu na score, cache'owany w `filterCache` (dobry do powtarzalnych ograniczeń, np. `archive:astro-ph`, `year:[2010 TO 2020]`). W wariancie Q1+fq Solr zwrócił numFound=9 449.

## 12. Co to eDisMax i po co `qf`, `pf`, `boost`?

Parser zapytań dla użytkowników: wiele pól z wagami (`qf=title^3 abstract`), premia za frazę (`pf`), tolerancyjny na błędy składni, obsługuje AND/OR/NOT; `boost` — mnożnik wyniku funkcją. U nas Q1–Q3 w eDisMax, `pf` dla frazy, `boost=exp(mul(0.08,sub(year,2025)))` w rozszerzeniu.

## 13. Facety kontra `GROUP BY` — co jest podobne, co inne?

Facet = liczności wartości pola dla zbioru trafień, liczone na docValues w tym samym żądaniu co wyszukiwanie; `GROUP BY` to osobne zapytanie agregujące po wyniku `@@`. U nas: `GROUP BY primary_category` / `archive` w PostgreSQL oraz `facet.field=primary_category&facet.field=archive` w Solrze. Liczności są zbliżone, ale nie identyczne, bo zbiory trafień różnią się o kilkadziesiąt dokumentów przez tokenizację (Q1: 2 tylko w SQL, 35 tylko w Solrze).

## 14. Czym jest commit w Solrze i dlaczego jeden na końcu?

Commit czyni zmiany widocznymi (otwiera nowy searcher) i utrwala segmenty. Częste commity (np. `autoSoftCommit` co 3 s w `_default`) spowalniają ładowanie, więc wyłączyliśmy auto-commity i robimy jeden na końcu: 100%: wysyłanie 213 s + commit 1,2 s.

## 15. Ile trwało ładowanie i indeksowanie w obu systemach?

100%: PostgreSQL COPY 242 s (z liczeniem `tsv`) + GIN 65 s; Solr 220 s razem. Rozmiar: PG tabela 2 438 MiB + indeksy 355 MiB; Solr 1 241 MiB po scaleniu segmentów.

## 16. Dlaczego w pomiarach Solra mierzycie z `cache=false`?

Powtórzone zapytanie wraca z `queryResultCache` (QTime ≈ 0 ms) — to nie mierzy dopasowania ani rankingu. Q1 top-10 przy 100%: z cache 0 ms, bez cache 7 ms (QTime), PostgreSQL 952 ms.

## 17. Jak mierzyliście czas i co to jest rozgrzany/zimny cache?

1 rozgrzewka + 5 pomiarów, mediana; SQL: `EXPLAIN (ANALYZE, BUFFERS)` i czas klienta, Solr: QTime i czas klienta. Zimny start: restart kontenerów + `drop_caches` w VM Dockera. Q1 count po restarcie: PG 21,0 s (rozgrzany 113 ms), Solr 100 ms.

## 18. Kiedy indeks w bazie wystarcza, a kiedy sięgnąć po Solra?

Baza: zbiór rzędu 10^6 rekordów (nasz pomiar), zapytania selektywne, jedno źródło prawdy, brak potrzeby facetów/podświetlania/zaawansowanego rankingu. Solr: ranking dużych zbiorów trafień, facety, hl, boosty, wyższe obciążenie. Koszt Solra: drugi system, spójność ewentualna, osobny schemat. Liczby: Q1 top-10 PG 952 ms vs Solr 7 ms; nie badaliśmy skalowania z rozmiarem zbioru, więc nie podajemy progu rekordów.

## 19. Jak działa boost rokiem i co zmienił w top-10?

Mnożnik `exp(0,08·(year−2025))` w Solrze (`boost=`) i w SQL (`ts_rank_cd * exp(…)`). Średni rok top-10 (PG przed→po): Q1 2 021,2→2 025,2, Solr: 2 014,0→2 025,8.

## 20. Czy dane były powielane? Jak wpływa to na wyniki?

Nie — wzięliśmy 1 000 000 rzeczywistych rekordów z arXiv (ponad 3 mln dostępnych), więc nie ma duplikatów w top-10 ani zawyżonych liczności facetów. (Duplikaty `id` w źródle — 83 — usunęliśmy przy przygotowaniu danych.)

## 21. Dlaczego Solr działa w trybie SolrCloud i co to zmieniło w projekcie?

Obraz `solr:10` startuje domyślnie w SolrCloud z wbudowanym ZooKeeperem. Konsekwencja: schemat i konfiguracja leżą w configsecie w ZK współdzielonym przez kolekcje, więc kolekcja (`papers_100`) ma własny configset (kopia `_default`); kolekcje tworzymy Collections API, schemat Schema API, config Config API.

## 22. Dlaczego `update.autoCreateFields=false`?

Wyłącza schemaless: nieznane pole w dokumencie powoduje błąd zamiast cichego utworzenia pola o domyślnym typie. Sprawdziliśmy: wysłanie dokumentu z nieistniejącym polem zwraca `unknown field`.

## 23. Jakie są ograniczenia Waszych pomiarów?

Jedna maszyna (Docker Desktop, 12 wątków, 2 GB sterty Solra), jeden węzeł; QTime ma rozdzielczość 1 ms; czas klienta Solra zawiera HTTP; porównanie rankingów tylko ilościowe (wspólne dokumenty), bez oceny trafności przez człowieka; „zimny” start to restart + drop_caches w VM, nie zimny dysk fizyczny.
