"""Pakuje archiwum do oddania: LAB3_<Nazwisko1>_<Imie1>_<Nazwisko2>_<Imie2>.zip (katalog dist/).

Uruchomienie:  python scripts/pack_zip.py --authors Langner Michal Nawrocki Jakub
Poziom oddawanej pracy: 3.0. Zawartość: kod (lab3/, scripts/), skrypty SQL (sql/), schemat Solra (solr/), README.md,
docs/zapytania_solr.md oraz pliki potrzebne do uruchomienia (docker-compose.yml, .env.example, requirements.txt).
Sprawozdanie PDF nie jest wymagane i nie trafia do archiwum; dodatkowe skrypty poziomu 5.0 (EXTRA_EXCLUDE) również nie.
BEZ: data/ (zbiór danych), results/, .env, venv/, __pycache__, .git, CLAUDE.md, pozostałe pliki docs/.
"""
import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIRS = ["lab3", "scripts", "sql", "solr"]
INCLUDE_FILES = ["README.md", "docs/zapytania_solr.md", "requirements.txt", "docker-compose.yml", ".env.example", ".gitignore"]
EXCLUDE_NAMES = {"__pycache__", ".pytest_cache"}
# pliki poziomu 5.0 (dodatkowe, poza oddawaną pracą) — ścieżki względem katalogu głównego
EXTRA_EXCLUDE = {
    "lab3/facets.py", "lab3/paging.py", "lab3/sync.py", "sql/03_sync.sql",
}
EXCLUDE_SUFFIX = {".pyc", ".tmp"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--authors", nargs=4, metavar=("NAZWISKO1", "IMIE1", "NAZWISKO2", "IMIE2"), default=["Langner", "Michal", "Nawrocki", "Jakub"],
                    help="Nazwisko1 Imie1 Nazwisko2 Imie2")
    args = ap.parse_args()
    name = "LAB3_" + "_".join(args.authors) + ".zip"
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / name
    files = [ROOT / f for f in INCLUDE_FILES if (ROOT / f).exists()]
    for d in INCLUDE_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and not (set(p.parts) & EXCLUDE_NAMES) and p.name not in EXCLUDE_NAMES and p.suffix not in EXCLUDE_SUFFIX and p.relative_to(ROOT).as_posix() not in EXTRA_EXCLUDE:
                files.append(p)
    missing = [f for f in INCLUDE_FILES if not (ROOT / f).exists()]
    if missing:
        print("UWAGA: brak plików: " + ", ".join(missing))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
    print(f"Zapisano {out} ({out.stat().st_size / 1024:.0f} KiB, {len(files)} plików)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
