"""Etap 7a (poziom 5.0): facety Solra (2 × facet.field + facet.range) kontra agregacje SQL (GROUP BY / GROUPING SETS).

Uruchomienie:  python -m lab3.facets [--sizes 10 50 100] [--repeats 5]
Przypadki:
  ALL      — cały zbiór (*:*), czyste porównanie agregacji,
  STRUCT   — filtr strukturalny archive=cs AND year>=2015 (identyczny zbiór dopasowanych dokumentów w obu systemach),
  Q1..Q3   — zbiory z zapytań pełnotekstowych (zbiory mogą różnić się o kilkadziesiąt dok. przez tokenizację).
Porównujemy: liczności (identyczne?) i czasy (mediana z 5): Solr (1 zapytanie) vs SQL 3×GROUP BY vs SQL GROUPING SETS.
Wynik: results/facets_vs_groupby.json
"""
import argparse
import sys
import time

from lab3.config import config
from lab3.db import pg_connect
from lab3.measure import REPEATS, nocache, now, save_json, solr_measure, solr_run, summarize
from lab3.queries import QUERIES

RANGE = {"start": 1990, "end": 2030, "gap": 5}
BUCKET = f"(CASE WHEN year >= {RANGE['start']} AND year < {RANGE['end']} " \
         f"THEN {RANGE['start']} + ((year - {RANGE['start']}) / {RANGE['gap']}) * {RANGE['gap']} END)"


def solr_params(q: str, fq: list[str] | None = None) -> dict:
    p = {"q": q, "rows": 0, "facet": "true", "facet.field": ["primary_category", "archive"],
         "facet.limit": -1, "facet.mincount": 1, "facet.sort": "index",
         "facet.range": "year", "facet.range.start": RANGE["start"], "facet.range.end": RANGE["end"],
         "facet.range.gap": RANGE["gap"], "facet.range.other": "before"}
    if fq:
        p["fq"] = fq
    return p


def solr_facets(js: dict) -> dict:
    fc = js["facet_counts"]
    out = {}
    for f in ("primary_category", "archive"):
        flat = fc["facet_fields"][f]
        out[f] = {flat[i]: flat[i + 1] for i in range(0, len(flat), 2)}
    flat = fc["facet_ranges"]["year"]["counts"]
    out["year"] = {int(flat[i]): flat[i + 1] for i in range(0, len(flat), 2) if flat[i + 1] > 0}
    return out


def sql_queries(t: str, where: str) -> dict:
    return {
        "primary_category": f"SELECT primary_category, count(*) FROM {t} WHERE {where} GROUP BY 1",
        "archive": f"SELECT archive, count(*) FROM {t} WHERE {where} GROUP BY 1",
        "year": f"SELECT {BUCKET} AS bucket, count(*) FROM {t} WHERE {where} AND year >= {RANGE['start']} GROUP BY 1",
        "grouping_sets": (
            f"SELECT primary_category, archive, bucket, count(*) FROM (SELECT primary_category, archive, {BUCKET} AS bucket "
            f"FROM {t} WHERE {where}) s GROUP BY GROUPING SETS ((primary_category), (archive), (bucket))"
        ),
    }


def timed_pg(conn, sql: str, repeats: int) -> tuple[list, dict]:
    conn.execute(sql).fetchall()
    server, client = [], []
    rows = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        rows = conn.execute(sql).fetchall()
        client.append((time.perf_counter() - t0) * 1000)
        plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql).fetchone()[0][0]
        server.append(plan["Execution Time"])
    return rows, {"exec_ms": summarize(server), "client_ms": summarize(client)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", default=["10", "50", "100"], choices=["10", "50", "100"])
    ap.add_argument("--repeats", type=int, default=REPEATS)
    args = ap.parse_args()
    cases = [("ALL", "*:*", None, "true"),
             ("STRUCT", "*:*", ["archive:cs", "year:[2015 TO *]"], "archive = 'cs' AND year >= 2015")]
    for k, q in QUERIES.items():
        cases.append((k, q.solr_q, None, f"tsv @@ {q.tsquery}"))
    results = []
    with pg_connect(autocommit=True) as conn:
        for size in args.sizes:
            t = f"papers_{size}"
            for name, sq, fq, where in cases:
                sp = solr_params(sq, fq)
                ms = solr_measure(t, nocache(sp), args.repeats, f"{name} facety (cache=false)", size)
                facets = solr_facets(solr_run(t, sp)["json"])
                sqls = sql_queries(t, where)
                sep, sep_time = {}, {"exec": 0.0, "client": 0.0, "exec_runs": None}
                per_query = {}
                for col in ("primary_category", "archive", "year"):
                    rows, tm = timed_pg(conn, sqls[col], args.repeats)
                    sep[col] = {r[0]: r[1] for r in rows if r[0] is not None}
                    per_query[col] = {"sql": sqls[col], **tm}
                    sep_time["exec"] += tm["exec_ms"]["median"]
                    sep_time["client"] += tm["client_ms"]["median"]
                rows, gs_time = timed_pg(conn, sqls["grouping_sets"], args.repeats)
                gs = {"primary_category": {}, "archive": {}, "year": {}}
                for pc, ar, bk, n in rows:
                    if pc is not None:
                        gs["primary_category"][pc] = n
                    elif ar is not None:
                        gs["archive"][ar] = n
                    elif bk is not None:
                        gs["year"][bk] = n
                gs_equal = all(gs[c] == sep[c] for c in sep)
                comparison = {}
                for col in ("primary_category", "archive", "year"):
                    a, b = facets[col], sep[col]
                    keys = set(a) | set(b)
                    comparison[col] = {"identical": a == b, "solr_values": len(a), "sql_values": len(b),
                                       "max_abs_diff": max((abs(a.get(k, 0) - b.get(k, 0)) for k in keys), default=0),
                                       "sum_solr": sum(a.values()), "sum_sql": sum(b.values())}
                results.append({
                    "size": size, "case": name, "solr_q": sq, "solr_fq": fq, "sql_where": where,
                    "solr_url": ms["query"], "solr_numFound": ms["result_count"],
                    "solr_qtime_ms": ms["qtime_ms"], "solr_client_ms": ms["client_ms"],
                    "sql_separate": per_query, "sql_separate_sum_exec_ms": round(sep_time["exec"], 3),
                    "sql_separate_sum_client_ms": round(sep_time["client"], 3),
                    "sql_grouping_sets": {"sql": sqls["grouping_sets"], **gs_time},
                    "grouping_sets_equals_separate": gs_equal, "comparison": comparison, "timestamp": now(),
                })
                c = comparison
                print(f"[{size}%] {name:6s} Solr QTime {ms['qtime_ms']['median']:>7} ms (klient {ms['client_ms']['median']:.1f}) | "
                      f"SQL 3×GROUP BY {sep_time['exec']:.1f} ms | GROUPING SETS {gs_time['exec_ms']['median']:.1f} ms | "
                      f"identyczne: cat={c['primary_category']['identical']} arch={c['archive']['identical']} year={c['year']['identical']}",
                      flush=True)
    save_json(config.results_dir / "facets_vs_groupby.json",
              {"timestamp": now(), "range": RANGE, "repeats": args.repeats, "results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())
