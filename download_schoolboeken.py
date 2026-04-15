#!/usr/bin/env python3
"""Download all PDFs from pascalgunsch.nl schoolboeken directories."""

import os
import urllib.parse
import urllib.request
from html.parser import HTMLParser


BASE = "https://files.pascalgunsch.nl/Middelbare%20Schoolboeken"
DEST = "/Users/jeroenmeij/Documents/schoolboeken"

DIRS = {
    "Wiskunde": "wiskunde",
    "Scheikunde": "scheikunde",
    "Natuurkunde": "natuurkunde",
}


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value.endswith(".pdf"):
                    self.links.append(value)


def download_pdfs(remote_dir: str, local_dir: str):
    os.makedirs(local_dir, exist_ok=True)
    url = f"{BASE}/{urllib.parse.quote(remote_dir)}/"

    with urllib.request.urlopen(url) as resp:
        html = resp.read().decode()

    parser = LinkExtractor()
    parser.feed(html)

    for link in parser.links:
        filename = urllib.parse.unquote(link)
        dest_path = os.path.join(local_dir, filename)
        file_url = url + link

        if os.path.exists(dest_path):
            print(f"  SKIP (exists): {filename}")
            continue

        print(f"  Downloading: {filename}")
        urllib.request.urlretrieve(file_url, dest_path)

    print(f"  Done — {len(parser.links)} file(s)\n")


if __name__ == "__main__":
    for remote, local in DIRS.items():
        print(f"[{remote}]")
        download_pdfs(remote, os.path.join(DEST, local))
    print("All done!")
