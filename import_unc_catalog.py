"""Import UNC undergraduate program listings and provisional course references.

Run: python3 -m pip install requests beautifulsoup4
     python3 import_unc_catalog.py

Existing manually curated requirements are never overwritten. Newly scraped
courses are NOT an official degree audit and must be checked against the catalog.
"""
import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Install dependencies first: python3 -m pip install requests beautifulsoup4")

BASE = Path(__file__).resolve().parent
ROOT = "https://catalog.unc.edu"
INDEX = ROOT + "/undergraduate/programs-study/"
CODE = re.compile(r"\b([A-Z]{2,6})\s+(\d{3}[A-Z]?)\b")
PROGRAM_PATH = re.compile(r"^/undergraduate/programs-study/[^/]+/$")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CarolinaDegreePlannerEducationalImporter/1.0 (catalog research; respectful rate limiting)"})


def fetch(url):
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def read_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def classify(name, url):
    s = (name + " " + url).lower()
    if "minor" in s:
        return "Minor"
    if "major" in s or "b.a." in s or "b.s." in s or "b.f.a." in s:
        return "Major"
    return None


def normalize_name(label, url):
    name = re.sub(r"\s+", " ", label).strip(" -–|\t\n")
    # Match the existing app naming style, e.g. "Economics B.S.".
    name = re.sub(r"\s+Major,?\s+(?=(?:B\.A\.|B\.S\.|B\.F\.A\.|B\.S\.P\.H\.))", " ", name, flags=re.I)
    name = re.sub(r",?\s+Major$", "", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def discover(soup):
    results = {}
    for a in soup.select("a[href]"):
        url = urljoin(INDEX, a.get("href", "")).split("#")[0].split("?")[0]
        p = urlparse(url)
        if p.netloc != "catalog.unc.edu" or not PROGRAM_PATH.match(p.path) or url == INDEX:
            continue
        label = a.get_text(" ", strip=True)
        kind = classify(label, p.path)
        if not kind or not label:
            continue
        name = normalize_name(label, url)
        if not name or len(name) > 140:
            continue
        # If catalog uses an ambiguous link label, prefer a subsequent better label.
        if url not in results or len(name) > len(results[url]["name"]):
            results[url] = {"name": name, "url": url, "type": kind}
    return sorted(results.values(), key=lambda x: (x["type"], x["name"]))


def catalog_references(soup):
    """Extract only references in catalog course tables/blocks, not all page text."""
    found = {}
    for container in soup.select("table.sc_courselist, .sc_courselist, .courseblock"):
        for row in container.select("tr") if container.name == "table" else [container]:
            text = row.get_text(" ", strip=True)
            for match in CODE.finditer(text):
                code = f"{match.group(1)} {match.group(2)}"
                if code not in found:
                    found[code] = {"code": code}
    return list(found.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Import first N discovered programs (0 = all)")
    parser.add_argument("--delay", type=float, default=0.8, help="Seconds between program requests")
    parser.add_argument("--dry-run", action="store_true", help="Show discovered programs without changing files")
    args = parser.parse_args()
    if args.delay < 0.5:
        parser.error("--delay must be at least 0.5 seconds")

    print("Reading UNC undergraduate catalog index...")
    try:
        programs = discover(fetch(INDEX))
    except requests.RequestException as exc:
        sys.exit(f"Could not reach UNC catalog: {exc}\nCheck your connection and try again.")
    if not programs:
        sys.exit("No program links found. UNC may have changed its catalog page layout; no files were modified.")
    if args.limit:
        programs = programs[:args.limit]
    print(f"Found {len(programs)} program links. Sample: {', '.join(p['name'] for p in programs[:5])}")
    if args.dry_run:
        for p in programs:
            print(f"{p['type']:5} {p['name']} — {p['url']}")
        return

    program_path = BASE / "unc_programs.json"
    requirement_path = BASE / "degree_requirements.json"
    existing_programs = read_json(program_path, [])
    existing_requirements = read_json(requirement_path, {})
    if not isinstance(existing_programs, list) or not isinstance(existing_requirements, dict):
        sys.exit("Existing JSON files have an unexpected format; no changes made.")

    by_name = {p.get("name"): p for p in existing_programs if isinstance(p, dict) and p.get("name")}
    added = 0
    imported = 0
    failures = []
    for i, program in enumerate(programs, 1):
        name = program["name"]
        if name not in by_name:
            by_name[name] = program
            added += 1
        if name in existing_requirements:
            print(f"[{i}/{len(programs)}] Preserve curated: {name}")
            continue
        try:
            soup = fetch(program["url"])
            courses = catalog_references(soup)
            existing_requirements[name] = {
                "source": program["url"],
                "verification_status": "Unverified automatic import",
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "requirements": [{
                    "name": "Catalog-listed course references (unverified)",
                    "description": "These courses were found in catalog course tables. They are NOT necessarily all required, and electives/alternatives, concentrations, credit rules, and prerequisites have not been validated. Verify against the official UNC catalog and advisor before relying on them.",
                    "courses": courses,
                }] if courses else [{
                    "name": "Requirements need manual review",
                    "description": "Program discovered, but no course table was parsed. Open the linked official catalog page to review requirements.",
                }],
            }
            imported += 1
            print(f"[{i}/{len(programs)}] Imported {name}: {len(courses)} provisional course references")
        except requests.RequestException as exc:
            failures.append((name, str(exc)))
            print(f"[{i}/{len(programs)}] Skipped {name}: {exc}")
        time.sleep(args.delay)

    write_json(program_path, sorted(by_name.values(), key=lambda p: p["name"]))
    write_json(requirement_path, existing_requirements)
    print(f"\nFinished: {added} new dropdown programs, {imported} new provisional requirement entries, {len(failures)} failed pages.")
    print("Original JSON files backed up as .json.bak. Your student progress and semester plan were not modified.")
    if failures:
        print("Failed pages (rerun to retry):", ", ".join(name for name, _ in failures))


if __name__ == "__main__":
    main()
