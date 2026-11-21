"""Buduje docs/sprawozdanie.pdf z docs/sprawozdanie.md.

Uruchomienie:  python scripts/build_pdf.py [--engine auto|browser|pandoc]

* browser (domyślnie w `auto`): Markdown -> HTML (pakiet `markdown`) -> PDF przez Chrome/Edge/Chromium w trybie
  headless (--print-to-pdf). Działa na Windows (Edge jest w systemie), macOS i Linux; polskie znaki i wykresy PNG działają
  bez dodatkowych narzędzi.
* pandoc: Markdown -> PDF przez Docker (obraz pandoc/latex, xelatex). Wymaga pobrania obrazu (~1-2 GB).
Przed budowaniem uruchom `python -m lab3.report`, który generuje sprawozdanie.md z results/.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "Segoe UI", "DejaVu Sans", Arial, sans-serif; font-size: 10.5pt; line-height: 1.42; color: #1b1b1b; }
h1 { font-size: 22pt; } h2 { font-size: 15pt; border-bottom: 1px solid #999; padding-bottom: 2px; margin-top: 22px; page-break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 16px; page-break-after: avoid; }
table { border-collapse: collapse; margin: 8px 0 12px 0; font-size: 8pt; width: 100%; page-break-inside: auto; }
th, td { border: 1px solid #aaa; padding: 2px 4px; vertical-align: top; }
th { background: #e8edf3; } tr { page-break-inside: avoid; }
code { font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 8.8pt; background: #f2f2f2; padding: 0 2px; }
pre { background: #f5f5f5; border: 1px solid #ddd; padding: 6px; font-size: 7.8pt; white-space: pre-wrap; word-break: break-word; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 7.8pt; }
img { max-width: 100%; display: block; margin: 8px auto; page-break-inside: avoid; }
blockquote { margin: 6px 0 10px 0; padding: 4px 10px; border-left: 3px solid #8aa; background: #f7fafb; font-size: 9.5pt; }
blockquote em { background: #fff2a8; font-style: normal; }
.title-page { text-align: center; margin-top: 90px; }
.title-page h1 { font-size: 26pt; margin: 40px 0; border: none; }
.title-page .uni { font-size: 14pt; letter-spacing: 1px; } .title-page .sub { font-size: 13pt; margin: 6px 0; }
.title-page .authors { margin-top: 70px; font-size: 14pt; } .title-page .date { margin-top: 40px; color: #555; }
.pb { page-break-after: always; }
.toc ul { list-style: none; padding-left: 18px; } .toc > ul { padding-left: 0; }
"""


def find_browser() -> str | None:
    cands = []
    if platform.system() == "Windows":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe", Path(base) / "Google/Chrome/Application/chrome.exe"]
    elif platform.system() == "Darwin":
        cands += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        w = shutil.which(name)
        if w:
            cands.append(Path(w))
    return next((str(c) for c in cands if c.exists()), None)


def build_browser() -> Path:
    import markdown

    browser = find_browser()
    if not browser:
        raise SystemExit("Nie znaleziono Chrome/Edge/Chromium — użyj --engine pandoc")
    md = (DOCS / "sprawozdanie.md").read_text(encoding="utf-8")
    html_body = markdown.markdown(md, extensions=["tables", "fenced_code", "toc", "sane_lists", "md_in_html"],
                                  extension_configs={"toc": {"title": "Spis treści", "toc_depth": "2-3"}})
    html = f'<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Sprawozdanie — Lab 3 PJN</title><style>{CSS}</style></head><body>{html_body}</body></html>'
    html_path = DOCS / "sprawozdanie.html"
    html_path.write_text(html, encoding="utf-8")
    pdf = DOCS / "sprawozdanie.pdf"
    if pdf.exists():
        pdf.unlink()
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
           f"--print-to-pdf={pdf}", html_path.as_uri()]
    subprocess.run(cmd, check=True, timeout=240, capture_output=True)
    html_path.unlink()  # HTML jest produktem pośrednim
    return pdf


def build_pandoc() -> Path:
    pdf = DOCS / "sprawozdanie.pdf"
    cmd = ["docker", "run", "--rm", "-v", f"{ROOT}:/data", "-w", "/data/docs", "pandoc/latex:latest", "sprawozdanie.md", "-o", "sprawozdanie.pdf",
           "--pdf-engine=xelatex", "-V", "mainfont=DejaVu Serif", "-V", "geometry:margin=2cm", "--toc", "--resource-path=/data/docs"]
    subprocess.run(cmd, check=True)
    return pdf


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["auto", "browser", "pandoc"], default="auto")
    args = ap.parse_args()
    engine = args.engine
    if engine == "auto":
        engine = "browser" if find_browser() else "pandoc"
    pdf = build_browser() if engine == "browser" else build_pandoc()
    print(f"Zapisano {pdf} ({pdf.stat().st_size / 1024:.0f} KiB), silnik: {engine}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
