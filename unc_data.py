
import json
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def main():
    catalog_url = (
        "https://catalog.unc.edu/undergraduate/programs-study/"
    )

    response = requests.get(
        catalog_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    programs = []
    seen_urls = set()

    # Collect links from the main undergraduate programs directory.
    for link in soup.select("a[href]"):
        name = link.get_text(" ", strip=True)
        href = link.get("href", "")

        if not name or not href:
            continue

        full_url = urljoin(catalog_url, href)

        if "/undergraduate/programs-study/" not in full_url:
            continue

        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)

        # Add a preliminary category based on the link name.
        name_lower = name.lower()

        if "minor" in name_lower:
            program_type = "Minor"
        elif (
            "philosophy, politics, and economics" in name_lower
            or "philosophy, politics & economics" in name_lower
        ):
            program_type = "Interdisciplinary Program"
        elif "b.a." in name_lower or "b.s." in name_lower:
            program_type = "Major"
        else:
            program_type = "Program"

        programs.append({
            "name": name,
            "url": full_url,
            "type": program_type
        })

    output_file = Path(__file__).parent / "unc_programs.json"

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            programs,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(f"Saved {len(programs)} catalog links.")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
