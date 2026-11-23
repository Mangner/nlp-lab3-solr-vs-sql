"""Pakuje archiwum do oddania: LAB3_<Nazwisko1>_<Imie1>_<Nazwisko2>_<Imie2>.zip (katalog dist/).

Uruchomienie:  python scripts/pack_zip.py [--authors Langner Michal Nawrocki Jakub]
Poziom oddawanej pracy: 3.0. Zawartość: moduły lab3/ potrzebne do poziomu 3.0 (MODULES), sql/, solr/, README.md,
docs/zapytania_solr.md, results/level3* (JSON, tabela, plany EXPLAIN) oraz docker-compose.yml, .env.example, requirements.txt.
BEZ: data/, .env, venv/, __pycache__, .git, CLAUDE.md, sprawozdania i ściągi, skryptów z poziomów 4.0/5.0 (level4, bench, cold, facets, paging, sync...).
"""
import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# moduły lab3 potrzebne do ścieżki prepare_data -> load_pg -> load_solr -> level3 (+ healthcheck)
MODULES = ["__init__", "config", "db", "solr", "healthcheck", "prepare_data", "load_pg", "load_solr", "queries", "measure", "level3"]
INCLUDE_FILES = ["README.md", "docs/zapytania_solr.md", "requirements.txt", "docker-compose.yml", ".env.example"]
INCLUDE_DIRS = ["sql", "solr"]
# poziom 5.0 (sql/03_sync.sql) nie wchodzi do archiwum
EXTRA_EXCLUDE = {"sql/03_sync.sql"}
EXCLUDE_NAMES = {"__pycache__", ".pytest_cache"}
EXCLUDE_SUFFIX = {".pyc", ".tmp"}


def collect() -> list[Path]:
    files = [ROOT / "lab3" / f"{m}.py" for m in MODULES]
    files += [ROOT / f for f in INCLUDE_FILES]
    for d in INCLUDE_DIRS:
        files += [p for p in sorted((ROOT / d).rglob("*")) if p.is_file()]
    res = ROOT / "results"
    files += sorted(res.glob("level3*"))
    files += sorted((res / "explain").glob("level3_*"))
    out = []
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        if (set(p.parts) & EXCLUDE_NAMES) or p.suffix in EXCLUDE_SUFFIX or rel in EXTRA_EXCLUDE or not p.is_file():
            continue
        out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--authors", nargs=4, metavar=("NAZWISKO1", "IMIE1", "NAZWISKO2", "IMIE2"), default=["Langner", "Michal", "Nawrocki", "Jakub"])
    args = ap.parse_args()
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / ("LAB3_" + "_".join(args.authors) + ".zip")
    missing = [f for f in INCLUDE_FILES + [f"lab3/{m}.py" for m in MODULES] if not (ROOT / f).exists()]
    if missing:
        print("BŁĄD: brak plików: " + ", ".join(missing))
        return 1
    files = collect()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
    print(f"Zapisano {out} ({out.stat().st_size / 1024:.0f} KiB, {len(files)} plików)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
