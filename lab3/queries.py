"""Definicje zapytań Q1–Q3 (poziom 3.0) w trzech wariantach: LIKE, FTS w PostgreSQL, Solr.

Wszystkie trzy metody przeszukują te same pola: title + abstract.
  * LIKE:  (title || ' ' || abstract) ILIKE '%…%'  — zwykły skan tabeli (bez indeksu trigramowego),
  * FTS:   tsv @@ <tsquery>                          — kolumna tsvector + indeks GIN,
  * Solr:  pole text_all (copyField z title i abstract), typ text_en.
"""
from dataclasses import dataclass, field

TXT = "(title || ' ' || abstract)"


def like(term: str) -> str:
    return f"{TXT} ILIKE '%{term}%'"


@dataclass(frozen=True)
class Query:
    key: str
    title: str                 # opis po polsku
    like_where: str            # warunek WHERE dla LIKE
    tsquery: str               # wyrażenie SQL zwracające tsquery
    solr_q: str                # q w parserze lucene, pole text_all
    solr_edismax_q: str        # q w eDisMax (qf podajemy osobno)
    solr_extra: dict = field(default_factory=dict)  # dodatkowe parametry eDisMax (np. pf dla frazy)


QUERIES = {
    "Q1": Query(
        "Q1", "słowo w dowolnej formie: simulate (simulated, simulates, simulating, simulation…)",
        like("simulate"),
        "plainto_tsquery('english', 'simulate')",
        "text_all:simulate",
        "simulate",
    ),
    "Q2": Query(
        "Q2", 'fraza "dark matter" (słowa obok siebie, w tej kolejności)',
        like("dark matter"),
        "phraseto_tsquery('english', 'dark matter')",
        'text_all:"dark matter"',
        '"dark matter"',
        {"pf": "title^3 abstract"},
    ),
    "Q3": Query(
        "Q3", "galaxy AND (cluster OR merger) AND NOT simulation",
        f"({like('galaxy')} AND ({like('cluster')} OR {like('merger')}) AND NOT {like('simulation')})",
        "to_tsquery('english', 'galaxy & (cluster | merger) & !simulation')",
        "text_all:galaxy AND (text_all:cluster OR text_all:merger) AND NOT text_all:simulation",
        "galaxy AND (cluster OR merger) AND NOT simulation",
    ),
}

# Wariant z filtrem (fq w Solrze): archiwum astro-ph i lata 2010–2020 — dla Q1.
FILTER_SQL = "archive = 'astro-ph' AND year BETWEEN 2010 AND 2020"
FILTER_SOLR_FQ = ["archive:astro-ph", "year:[2010 TO 2020]"]

SIZES = ["10", "50", "100"]
EDISMAX_QF = "title^3 abstract"
TOP_FL = "id,title,primary_category,archive,year,score"


# ------------------------------------------------------------------------------------------ poziom 4.0 / 5.0
YEAR_BOOST_SQL = "exp(0.08 * (year - 2025))"          # każdy rok wstecz zmniejsza wynik o ~8%
YEAR_BOOST_SOLR = "exp(mul(0.08,sub(year,2025)))"      # ta sama funkcja po stronie Solra (parametr boost eDisMax)


def count_sql(table: str, where: str) -> str:
    return f"SELECT count(*) FROM {table} WHERE {where}"


def top_sql(table: str, q: Query, limit: int = 10, boost: bool = False, offset: int = 0, norm: int = 0) -> str:
    """Ranking ts_rank_cd (waga A tytułu = 1.0, B abstraktu = 0.4); opcjonalnie przemnożony przez funkcję roku."""
    factor = f" * {YEAR_BOOST_SQL}" if boost else ""
    n = f", {norm}" if norm else ""
    off = f" OFFSET {offset}" if offset else ""
    return (f"SELECT id, title, year, primary_category, ts_rank_cd(tsv, s.q{n}){factor} AS rank "
            f"FROM {table}, (SELECT {q.tsquery} AS q) s WHERE tsv @@ s.q "
            f"ORDER BY rank DESC, id ASC LIMIT {limit}{off}")


def group_sql(table: str, q: Query, column: str, limit: int = 10) -> str:
    return (f"SELECT {column}, count(*) AS n FROM {table} WHERE tsv @@ {q.tsquery} "
            f"GROUP BY {column} ORDER BY n DESC, {column} LIMIT {limit}")


def edismax_params(q: Query, rows: int = 10, boost: bool = False, extra: dict | None = None) -> dict:
    p = {"defType": "edismax", "q": q.solr_edismax_q, "qf": EDISMAX_QF, "fl": TOP_FL, "rows": rows,
         "sort": "score desc, id asc"}
    p.update(q.solr_extra)
    if boost:
        p["boost"] = YEAR_BOOST_SOLR
    if extra:
        p.update(extra)
    return p
