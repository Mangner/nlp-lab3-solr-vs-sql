"""Etap 8: wykresy (matplotlib, PNG 170 dpi) generowane wyłącznie z plików w results/.

Uruchomienie:  python -m lab3.figures   ->  results/figures/*.png   (wykresy do sprawozdania poziomu 4.0)
               python -m lab3.figures --extra   dodatkowo wykresy poziomu 5.0 (nie wchodzą do oddawanego sprawozdania)
"""
import argparse
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from lab3.config import config  # noqa: E402

R = config.results_dir
OUT = R / "figures"
# paleta odporna na daltonizm (Okabe–Ito): LIKE / FTS w PostgreSQL / Solr
C = {"LIKE": "#D55E00", "FTS": "#0072B2", "Solr": "#009E73", "Solr+cache": "#8FCFB8", "ink": "#333333"}
LABEL = {"LIKE": "LIKE (skan tabeli)", "FTS": "PostgreSQL FTS (GIN)", "Solr": "Solr (cache=false)", "Solr+cache": "Solr (z cache wyników)"}
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "figure.dpi": 100, "savefig.dpi": 170,
                     "font.family": "DejaVu Sans"})


def load(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)
    print("Zapisano", OUT / name)


def val(m):
    return m["exec_ms"]["median"] if "exec_ms" in m else m["qtime_ms"]["median"]


def scaling(mode: str, methods: list[str], fname: str, title: str):
    bm = load("benchmark.json")["measurements"]
    sizes = ["10", "50", "100"]
    xs = [100_000, 500_000, 1_000_000]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True)
    for ax, key in zip(axes, ["Q1", "Q2", "Q3"]):
        for meth in methods:
            ys = []
            for s in sizes:
                m = next(x for x in bm if x["size"] == s and x["query_key"] == key and x["mode"] == mode and x["method"] == meth)
                # czas klienta dla Solra (QTime ma rozdzielczość 1 ms, bywa 0), czas serwera dla SQL
                ys.append(m["client_ms"]["median"] if meth.startswith("Solr") else val(m))
            ax.plot(xs, [max(y, 0.5) for y in ys], marker="o", color=C[meth], label=LABEL[meth],
                    linestyle="--" if meth == "Solr+cache" else "-")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xticks(xs)
        ax.set_xticklabels(["100 tys.", "500 tys.", "1 mln"])
        ax.set_title(key)
        ax.set_xlabel("liczba rekordów")
    axes[0].set_ylabel("czas [ms], skala log.")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=len(methods), fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.08))
    fig.suptitle(title, y=1.02)
    save(fig, fname)


def loading():
    pg = [t for t in load("load_pg.json")["tables"] if t["table"] == "papers_100"]
    sr = [c for c in load("load_solr.json")["collections"] if c["collection"] == "papers_100"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    lab = ["zbiór 100% (1 mln rekordów)"]
    x = range(1)
    ax = axes[0]
    ax.bar([i - 0.2 for i in x], [t["copy_seconds"] for t in pg], 0.4, color=C["FTS"], label="PG: COPY (z liczeniem tsvector)")
    ax.bar([i - 0.2 for i in x], [t["gin_seconds"] for t in pg], 0.4, bottom=[t["copy_seconds"] for t in pg], color="#7FB5D9", label="PG: budowa indeksu GIN")
    ax.bar([i + 0.2 for i in x], [c["send_seconds"] for c in sr], 0.4, color=C["Solr"], label="Solr: wysyłanie paczek /update")
    ax.bar([i + 0.2 for i in x], [c["commit_seconds"] for c in sr], 0.4, bottom=[c["send_seconds"] for c in sr], color="#8FCFB8", label="Solr: commit")
    ax.set_xticks(list(x))
    ax.set_xticklabels(lab)
    ax.set_ylabel("czas [s]")
    ax.set_title("Czas ładowania i indeksowania")
    ax.legend(fontsize=7.5)
    ax = axes[1]
    mb = 2**20
    ax.bar([i - 0.2 for i in x], [t["table_bytes_with_toast"] / mb for t in pg], 0.4, color="#7FB5D9", label="PG: tabela (z TOAST, z kolumną tsv)")
    ax.bar([i - 0.2 for i in x], [t["indexes_bytes"] / mb for t in pg], 0.4, bottom=[t["table_bytes_with_toast"] / mb for t in pg], color=C["FTS"], label="PG: indeksy (GIN + B-tree + PK)")
    ax.bar([i + 0.2 for i in x], [c.get("index_bytes_settled", c["index_bytes"]) / mb for c in sr], 0.4, color=C["Solr"], label="Solr: indeks po scaleniu segmentów")
    ax.set_xticks(list(x))
    ax.set_xticklabels(lab)
    ax.set_ylabel("rozmiar [MiB]")
    ax.set_title("Rozmiar na dysku")
    ax.legend(fontsize=7.5)
    save(fig, "ladowanie.png")


def times100():
    bm = load("benchmark.json")["measurements"]

    def get(q, mode, meth):
        return next(x for x in bm if x["size"] == "100" and x["query_key"] == q and x["mode"] == mode and x["method"] == meth)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, mode, meths, ttl in ((axes[0], "count", ["LIKE", "FTS", "Solr"], "Zliczanie trafień"),
                                 (axes[1], "top10", ["FTS", "Solr"], "Top-10 wg trafności")):
        w = 0.8 / len(meths)
        for j, meth in enumerate(meths):
            vals = [val(get(q, mode, meth)) for q in ("Q1", "Q2", "Q3")]
            # QTime ma rozdzielczość 1 ms; 0 rysujemy jako 0,5 (skala log)
            bars = ax.bar([i + (j - (len(meths) - 1) / 2) * w for i in range(3)], [max(v, 0.5) for v in vals], w,
                          color=C[meth], label=LABEL[meth])
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, max(v, 0.5) * 1.1, f"{v:.0f}", ha="center", fontsize=7.5)
        ax.set_yscale("log")
        ax.set_xticks(range(3))
        ax.set_xticklabels(["Q1", "Q2", "Q3"])
        ax.set_ylabel("czas serwera [ms], skala log")
        ax.set_title(ttl + " (1 mln rekordów, mediana z 5)")
        ax.set_ylim(0.3, ax.get_ylim()[1] * 2)
        ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    save(fig, "czasy_100.png")


def facets():
    res = [r for r in load("facets_vs_groupby.json")["results"] if r["size"] == "100"]
    cases = [r["case"] for r in res]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    w = 0.27
    xs = range(len(res))
    ax.bar([i - w for i in xs], [r["sql_separate_sum_exec_ms"] for r in res], w, color=C["LIKE"], label="SQL: 3 × GROUP BY (suma)")
    ax.bar(list(xs), [r["sql_grouping_sets"]["exec_ms"]["median"] for r in res], w, color=C["FTS"], label="SQL: GROUPING SETS (1 zapytanie)")
    ax.bar([i + w for i in xs], [r["solr_client_ms"]["median"] for r in res], w, color=C["Solr"], label="Solr: 1 zapytanie (2×facet.field + facet.range), czas klienta")
    ax.set_yscale("log")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{c}\n({r['solr_numFound']:,} dok.)".replace(",", " ") for c, r in zip(cases, res)])
    ax.set_ylabel("czas [ms], skala log.")
    ax.set_title("Facety Solra a agregacje SQL — zbiór 100% (mediana z 5)")
    ax.legend(fontsize=8)
    save(fig, "facety_vs_groupby.png")


def paging():
    d = load("paging.json")
    rs = d["results"]
    xs = [r["depth"] for r in rs]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(xs, [r["solr_start_rows"]["client_ms"]["median"] for r in rs], marker="o", color=C["LIKE"], label="Solr start/rows")
    ax.plot(xs, [r["solr_cursor"]["client_ms"]["median"] for r in rs], marker="o", color=C["Solr"], label="Solr cursorMark")
    ax.plot(xs, [r["sql_offset"]["client_ms"]["median"] for r in rs], marker="o", color=C["FTS"], label="PostgreSQL OFFSET/LIMIT")
    ax.set_yscale("log")
    ax.set_xscale("symlog", linthresh=1000)
    ax.set_xlim(-30, 8e5)
    ax.set_xlabel(f"głębokość (pozycja początku strony), strona = {d['rows']} dok.")
    ax.set_ylabel("czas pobrania strony [ms], skala log.")
    ax.set_title(f"Głębokie stronicowanie (łącznie {d['numFound']:,} trafień)".replace(",", " "))
    ax.legend()
    save(fig, "stronicowanie.png")


def boost():
    b = load("level4_boost.json")["queries"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    for ax, eng, name in ((axes[0], "pg", "PostgreSQL (ts_rank_cd)"), (axes[1], "solr", "Solr (eDisMax)")):
        xs = range(3)
        before = [b[k]["year_stats"][f"{eng}_before"]["top10_mean_year"] for k in ("Q1", "Q2", "Q3")]
        after = [b[k]["year_stats"][f"{eng}_after"]["top10_mean_year"] for k in ("Q1", "Q2", "Q3")]
        ax.bar([i - 0.2 for i in xs], before, 0.4, color="#9AA5B1", label="bez boostu")
        ax.bar([i + 0.2 for i in xs], after, 0.4, color=C["FTS"] if eng == "pg" else C["Solr"], label="z boostem rokiem")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(["Q1", "Q2", "Q3"])
        ax.set_ylim(1995, 2028)
        ax.set_title(name)
        ax.legend(fontsize=8, loc="lower right")
    axes[0].set_ylabel("średni rok publikacji w top-10")
    save(fig, "boost_rok.png")


def cold():
    d = load("cold.json")["results"]
    bm = load("benchmark.json")["measurements"]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    keys = [("FTS count", "FTS", "count"), ("Solr count", "Solr", "count")]
    labels, cold_v, warm_v, cols = [], [], [], []
    for q in ("Q1", "Q2", "Q3"):
        for name, meth, mode in keys:
            c0 = next(x for x in d if x["query_key"] == q and x["method"] == name)["first_run_client_ms"]
            m = next(x for x in bm if x["size"] == "100" and x["query_key"] == q and x["mode"] == mode and x["method"] == meth)
            labels.append(f"{q}\n{'PG FTS' if meth == 'FTS' else 'Solr'}")
            cold_v.append(c0)
            warm_v.append(m["client_ms"]["median"])
            cols.append(C[meth])
    xs = range(len(labels))
    ax.bar([i - 0.2 for i in xs], cold_v, 0.4, color=cols, alpha=0.45, label="1. wykonanie po restarcie (zimne)")
    ax.bar([i + 0.2 for i in xs], warm_v, 0.4, color=cols, label="mediana, rozgrzany cache")
    ax.set_yscale("log")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("czas klienta [ms], skala log.")
    ax.set_title("Zimny start a rozgrzany cache — zbiór 100%, zapytanie count")
    ax.legend(fontsize=8)
    save(fig, "zimny_start.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", action="store_true", help="dodatkowe wykresy poziomu 5.0 (skalowanie, facety, stronicowanie)")
    args = ap.parse_args()
    times100()
    loading()
    boost()
    cold()
    if args.extra:
        scaling("count", ["LIKE", "FTS", "Solr", "Solr+cache"], "skalowanie_count.png",
                "Skalowanie: czas zliczania trafień (LIKE, FTS, Solr) — mediana z 5")
        scaling("top10", ["FTS", "Solr", "Solr+cache"], "skalowanie_top10.png",
                "Skalowanie: top-10 wg trafności (ts_rank_cd vs eDisMax) — mediana z 5")
        facets()
        paging()
    return 0


if __name__ == "__main__":
    sys.exit(main())
