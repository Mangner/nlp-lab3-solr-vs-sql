"""Etap 6 (poziom 4.0): ranking, GROUP BY vs facety, podświetlanie, porównanie top-10, boost rokiem.

Uruchomienie:  python -m lab3.level4 [--size 100]
Wyniki: results/level4.json (funkcjonalne), results/level4_boost.json (rozszerzenie: boost trafności rokiem).
Pomiary czasu zapytań (mediana z 5) robi lab3.bench; tu zapisujemy zapytania, wyniki i liczby do porównań.
"""
import argparse
import statistics
import sys
import time
from collections import Counter

from lab3.config import config
from lab3.db import pg_connect
from lab3.measure import now, save_json, solr_run
from lab3.queries import QUERIES, edismax_params, group_sql, top_sql

HL = {"hl": "true", "hl.fl": "abstract,title", "hl.method": "unified", "hl.snippets": 2, "hl.fragsize": 220,
      "hl.tag.pre": "<em>", "hl.tag.post": "</em>", "hl.requireFieldMatch": "false"}
FACETS = {"facet": "true", "facet.field": ["primary_category", "archive"], "facet.limit": 10,
          "facet.mincount": 1, "facet.sort": "count"}


def pg_top(conn, sql: str):
    cols = ["id", "title", "year", "primary_category", "score"]
    return [dict(zip(cols, r)) for r in conn.execute(sql).fetchall()]


def facet_pairs(js: dict, field: str):
    flat = js["facet_counts"]["facet_fields"][field]
    return [[flat[i], flat[i + 1]] for i in range(0, len(flat), 2)]


def decade_hist(years: list[int]) -> dict:
    return dict(sorted(Counter((y // 5) * 5 for y in years).items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="100", choices=["10", "50", "100"])
    args = ap.parse_args()
    t = f"papers_{args.size}"
    functional, boost_res = {}, {}
    with pg_connect(autocommit=True) as conn:
        for key, q in QUERIES.items():
            sql_top = top_sql(t, q)
            pg10 = pg_top(conn, sql_top)
            pg100 = pg_top(conn, top_sql(t, q, limit=100))
            sp = edismax_params(q)
            r = solr_run(t, {**sp, **FACETS, **HL})
            solr10 = r["docs"]
            solr100 = solr_run(t, edismax_params(q, rows=100))["docs"]
            ids_pg, ids_sr = [d["id"] for d in pg10], [d["id"] for d in solr10]
            # wariant PG z normalizacją długości dokumentu (flaga 2 = dzielenie przez długość) — wyjaśnienie różnic
            pg10_n2 = pg_top(conn, top_sql(t, q, norm=2))
            pg100_n2 = pg_top(conn, top_sql(t, q, limit=100, norm=2))
            common = [i for i in ids_pg if i in ids_sr]
            common100 = len({d["id"] for d in pg100} & {d["id"] for d in solr100})

            # GROUP BY vs facety (ten sam zbiór dopasowanych dokumentów)
            groups = {}
            for col in ("primary_category", "archive"):
                gsql = group_sql(t, q, col)
                groups[col] = {"sql": gsql, "rows": [list(x) for x in conn.execute(gsql).fetchall()],
                               "solr_facet": facet_pairs(r["json"], col)}

            # podświetlanie: Solr (unified highlighter) vs ts_headline w PG dla tych samych top-3 dokumentów
            hl = r["json"].get("highlighting", {})
            hl_pg = []
            ts_head_sql = ("SELECT id, ts_headline('english', abstract, s.q, "
                           "'MaxFragments=2, MaxWords=35, MinWords=15, StartSel=<em>, StopSel=</em>') "
                           f"FROM {t}, (SELECT {q.tsquery} AS q) s WHERE id = ANY(%s)")
            t0 = time.perf_counter()
            rows_h = conn.execute(ts_head_sql, (ids_pg[:10],)).fetchall()
            ts_head_ms = (time.perf_counter() - t0) * 1000
            head_map = dict(rows_h)
            for i in ids_pg[:3]:
                hl_pg.append({"id": i, "ts_headline": head_map.get(i)})
            functional[key] = {
                "title": q.title,
                "pg_top10_sql": sql_top, "pg_top10": pg10,
                "solr_top10_url": r["url"], "solr_top10": solr10,
                "common_top10": common, "common_top10_count": len(common),
                "common_top100_count": common100,
                "pg_top10_norm2_sql": top_sql(t, q, norm=2), "pg_top10_norm2": pg10_n2,
                "common_top10_count_pg_norm2": len({d["id"] for d in pg10_n2} & set(ids_sr)),
                "common_top100_count_pg_norm2": len({d["id"] for d in pg100_n2} & {d["id"] for d in solr100}),
                "mean_abstract_len_top10": {},
                "numFound_solr": r["numFound"],
                "group_by_vs_facets": groups,
                "highlighting": {"solr": {i: hl.get(i) for i in ids_sr[:3]}, "pg_ts_headline": hl_pg,
                                 "pg_ts_headline_sql": ts_head_sql, "pg_ts_headline_10docs_ms": round(ts_head_ms, 2)},
                "timestamp": now(),
            }
            lens = lambda ids: statistics.fmean(  # noqa: E731
                r[0] for r in conn.execute(f"SELECT length(abstract) FROM {t} WHERE id = ANY(%s)", (ids,)))
            functional[key]["mean_abstract_len_top10"] = {
                "pg_ts_rank_cd": round(lens(ids_pg), 1), "pg_norm2": round(lens([d["id"] for d in pg10_n2]), 1),
                "solr_edismax": round(lens(ids_sr), 1)}
            print(f"{key}: wspólne top-10: {len(common)}, top-100: {common100}; PG norm2: "
                  f"{functional[key]['common_top10_count_pg_norm2']} / {functional[key]['common_top100_count_pg_norm2']}")

            # --- rozszerzenie: boost rokiem ---
            pgb10 = pg_top(conn, top_sql(t, q, boost=True))
            pgb100 = pg_top(conn, top_sql(t, q, limit=100, boost=True))
            sb = solr_run(t, edismax_params(q, boost=True))
            sb100 = solr_run(t, edismax_params(q, rows=100, boost=True))["docs"]
            years = lambda docs: [d["year"] for d in docs]  # noqa: E731
            boost_res[key] = {
                "title": q.title,
                "pg_before": pg10, "pg_after": pgb10, "solr_before": solr10, "solr_after": sb["docs"],
                "pg_sql_boosted": top_sql(t, q, boost=True), "solr_url_boosted": sb["url"],
                "year_stats": {
                    name: {"top10_mean_year": round(statistics.fmean(years(docs[:10])), 2),
                           "top10_median_year": statistics.median(years(docs[:10])),
                           "top100_mean_year": round(statistics.fmean(years(docs)), 2),
                           "top10_hist_5y": decade_hist(years(docs[:10])),
                           "top100_hist_5y": decade_hist(years(docs))}
                    for name, docs in (("pg_before", pg100), ("pg_after", pgb100),
                                       ("solr_before", solr100), ("solr_after", sb100))
                },
                "overlap_top10_after": len({d["id"] for d in pgb10} & {d["id"] for d in sb["docs"]}),
                "overlap_top10_pg_before_after": len({d["id"] for d in pg10} & {d["id"] for d in pgb10}),
                "overlap_top10_solr_before_after": len({d["id"] for d in solr10} & {d["id"] for d in sb["docs"]}),
            }
            # słownik year_stats dla top-10 liczony na pierwszych 10 elementach top-100
    save_json(config.results_dir / "level4.json", {"size": args.size, "timestamp": now(), "queries": functional})
    save_json(config.results_dir / "level4_boost.json", {"size": args.size, "timestamp": now(), "queries": boost_res})
    return 0


if __name__ == "__main__":
    sys.exit(main())
