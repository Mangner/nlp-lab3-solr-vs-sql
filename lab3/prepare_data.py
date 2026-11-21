"""Etap 2: pobranie metadanych arXiv z Hugging Face i przygotowanie zbiorów 10% / 50% / 100%.

Uruchomienie:  python -m lab3.prepare_data [--limit N] [--out KATALOG]

Algorytm (dwa przebiegi po plikach parquet, bez trzymania całości w pamięci):
  1. przebieg 1: dla każdego rekordu liczymy rok, filtrujemy, usuwamy powtórzone id i zapamiętujemy tylko (klucz_losowy, id);
     klucz = skrót blake2b(seed:id), więc wybór jest deterministyczny;
  2. wybieramy N rekordów o najmniejszym kluczu (100%); 10% i 50% to N/10 i N/2 najmniejszych kluczy,
     dzięki czemu 10% ⊂ 50% ⊂ 100%;
  3. przebieg 2: strumieniowo zapisujemy wybrane rekordy do CSV (dla COPY) i JSONL (dla Solra).
Pominięte pola z danymi osobowymi: authors, authors_parsed, submitter.
"""
import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import snapshot_download
from tqdm import tqdm

from lab3.config import config

REPO = "librarian-bots/arxiv-metadata-snapshot"
MIN_ABSTRACT = 300
YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
COLUMNS = ["id", "title", "categories", "license", "abstract", "versions", "update_date"]
SIZES = {"10": 0.10, "50": 0.50, "100": 1.0}
CSV_FIELDS = ["id", "title", "abstract", "primary_category", "archive", "categories", "year", "license"]


def norm(s: str) -> str:
    return " ".join((s or "").split())


def first_year(versions, update_date):
    """Rok pierwszej wersji (v1) z pola versions[].created; fallback: update_date."""
    best = None
    for v in versions or []:
        m = YEAR_RE.search(v.get("created") or "")
        if m:
            y = int(m.group(1))
            best = y if best is None else min(best, y)
    if best is None and update_date is not None:
        best = update_date.year
    return best


def make_record(row):
    abstract = norm(row["abstract"])
    title = norm(row["title"])
    cats = (row["categories"] or "").split()
    year = first_year(row["versions"], row["update_date"])
    if len(abstract) < MIN_ABSTRACT or not title or not cats or year is None:
        return None
    primary = cats[0]
    return {
        "id": row["id"], "title": title, "abstract": abstract,
        "primary_category": primary, "archive": primary.split(".")[0],
        "categories": cats, "year": year, "license": norm(row["license"] or "") or "none",
    }


def rank_key(seed: int, rid: str) -> int:
    return int.from_bytes(hashlib.blake2b(f"{seed}:{rid}".encode(), digest_size=8).digest(), "big")


def pg_array(items):
    return "{" + ",".join(items) + "}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=config.num_records, help="liczba rekordów zbioru 100%%")
    ap.add_argument("--out", default=None, help="katalog wyjściowy (domyślnie DATA_DIR)")
    args = ap.parse_args()
    out = Path(args.out) if args.out else config.data_dir
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = config.data_dir / "raw"

    print(f"Pobieranie {REPO} (pliki już pobrane są pomijane)...")
    snapshot_download(REPO, repo_type="dataset", local_dir=raw_dir, allow_patterns=["data/*.parquet", "README.md"])
    shards = sorted((raw_dir / "data").glob("*.parquet"))
    print(f"Plików parquet: {len(shards)}")

    # --- przebieg 1 ---
    t0 = time.time()
    total = valid = dupes = 0
    seen = set()
    keys = []  # (klucz, id)
    for sh in tqdm(shards, desc="przebieg 1 (filtrowanie)"):
        pf = pq.ParquetFile(sh)
        for batch in pf.iter_batches(batch_size=50_000, columns=COLUMNS):
            for row in batch.to_pylist():
                total += 1
                rec = make_record(row)
                if rec and rec["id"] in seen:
                    dupes += 1  # źródło zawiera powtórzone id — zostawiamy pierwsze wystąpienie
                elif rec:
                    seen.add(rec["id"])
                    valid += 1
                    keys.append((rank_key(config.random_seed, rec["id"]), rec["id"]))
    keys.sort()
    n100 = min(args.limit, len(keys))
    cut = {name: int(n100 * frac) for name, frac in SIZES.items()}
    rank_of = {rid: i for i, (_, rid) in enumerate(keys[:n100])}
    del keys, seen
    print(f"Rekordów w źródle: {total}, po filtrach i deduplikacji: {valid} (zduplikowane id: {dupes}); wybieramy {n100} "
          f"(10%={cut['10']}, 50%={cut['50']}) [{time.time() - t0:.0f} s]")

    # --- przebieg 2 ---
    files, writers = {}, {}
    for name in SIZES:
        fc = open(out / f"papers_{name}.csv", "w", encoding="utf-8", newline="")
        fj = open(out / f"papers_{name}.jsonl", "w", encoding="utf-8", newline="\n")
        files[name] = (fc, fj)
        w = csv.writer(fc, quoting=csv.QUOTE_MINIMAL)
        w.writerow(CSV_FIELDS)
        writers[name] = w
    stats = {n: {"count": 0, "abs_len": [], "cat": Counter(), "arch": Counter(), "lic": Counter(), "year": Counter()}
             for n in SIZES}
    example = None
    written = 0
    pbar = tqdm(total=n100, desc="przebieg 2 (zapis)")
    for sh in shards:
        pf = pq.ParquetFile(sh)
        for batch in pf.iter_batches(batch_size=50_000, columns=COLUMNS):
            for row in batch.to_pylist():
                if row["id"] not in rank_of:
                    continue
                rec = make_record(row)
                if rec is None:  # to samo id mogło wystąpić wcześniej w wersji nieprawidłowej — zob. przebieg 1
                    continue
                rank = rank_of.pop(row["id"])  # pop: każdy id zapisujemy tylko raz
                if example is None and rank == 0:
                    example = rec
                csv_row = [rec["id"], rec["title"], rec["abstract"], rec["primary_category"], rec["archive"],
                           pg_array(rec["categories"]), rec["year"], rec["license"]]
                line = json.dumps(rec, ensure_ascii=False)
                for name in SIZES:
                    if rank < cut[name]:
                        writers[name].writerow(csv_row)
                        files[name][1].write(line + "\n")
                        s = stats[name]
                        s["count"] += 1
                        s["abs_len"].append(len(rec["abstract"]))
                        s["cat"][rec["primary_category"]] += 1
                        s["arch"][rec["archive"]] += 1
                        s["lic"][rec["license"]] += 1
                        s["year"][rec["year"]] += 1
                written += 1
                pbar.update(1)
    pbar.close()
    for fc, fj in files.values():
        fc.close()
        fj.close()
    assert written == n100, (written, n100)

    result = {
        "source": REPO, "source_license": "CC0 (metadane arXiv, Cornell University)",
        "seed": config.random_seed, "min_abstract_chars": MIN_ABSTRACT,
        "source_records": total, "duplicate_ids_dropped": dupes, "records_after_filters": valid,
        "datasets": {},
        "example_record": example,
    }
    for name, s in stats.items():
        L = s["abs_len"]
        result["datasets"][f"papers_{name}"] = {
            "records": s["count"],
            "abstract_len_mean": round(statistics.fmean(L), 1),
            "abstract_len_median": statistics.median(L),
            "csv_bytes": (out / f"papers_{name}.csv").stat().st_size,
            "jsonl_bytes": (out / f"papers_{name}.jsonl").stat().st_size,
            "distinct_primary_category": len(s["cat"]),
            "distinct_archive": len(s["arch"]),
            "distinct_license": len(s["lic"]),
            "top_primary_category": s["cat"].most_common(15),
            "top_archive": s["arch"].most_common(15),
            "licenses": s["lic"].most_common(),
            "year_distribution": sorted(s["year"].items()),
        }
    stats_path = (config.results_dir if out == config.data_dir else out) / "dataset_stats.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Zapisano statystyki: {stats_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
