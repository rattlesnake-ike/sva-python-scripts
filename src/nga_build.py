"""One-time NGA open-data import: downloads the CC0 CSVs from GitHub and builds
data/nga.sqlite for fast local keyword search (no NGA search API needed).

Run:  python nga_build.py        (downloads ~170MB once, takes a few minutes)
Uses only stdlib (urllib + csv + sqlite3). Re-run anytime to refresh.
"""
import csv
import os
import sqlite3
import sys
import urllib.request

csv.field_size_limit(sys.maxsize)

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

OBJECTS = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/objects.csv"
IMAGES = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/published_images.csv"

def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last_pct = 0, -1
        while True:
            chunk = r.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total:
                pct = got * 100 // total
                if pct // 10 != last_pct // 10:
                    last_pct = pct
                    print(f"  {os.path.basename(dest)}: {pct}% ({got // 1048576}MB)", flush=True)
    print(f"  saved {dest} ({os.path.getsize(dest) // 1048576}MB)", flush=True)

def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0

def build():
    print("downloading NGA open data (one-time, ~170MB)...", flush=True)
    download(OBJECTS, os.path.join(DATA, "objects.csv"))
    download(IMAGES, os.path.join(DATA, "published_images.csv"))

    print("indexing objects...", flush=True)
    objs = {}
    with open(os.path.join(DATA, "objects.csv"), encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            oid = (row.get("objectid") or "").strip()
            if oid:
                objs[oid] = row
    print(f"  {len(objs)} objects", flush=True)

    db_path = os.path.join(DATA, "nga.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""CREATE TABLE nga(objectid TEXT PRIMARY KEY, title TEXT,
        displaydate TEXT, beginyear INT, endyear INT, artist TEXT, medium TEXT,
        class TEXT, credit TEXT, uuid TEXT, iiif TEXT, iiifthumb TEXT, assist TEXT)""")
    n = 0
    with open(os.path.join(DATA, "published_images.csv"), encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("openaccess") or "").strip() != "1":
                continue
            if (row.get("viewtype") or "").strip().lower() != "primary":
                continue
            oid = (row.get("depictstmsobjectid") or "").strip()
            o = objs.get(oid)
            if o is None:
                continue
            cur.execute(
                "INSERT OR IGNORE INTO nga VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, o.get("title", ""), o.get("displaydate", ""),
                 to_int(o.get("beginyear")), to_int(o.get("endyear")),
                 o.get("attribution", ""), o.get("medium", ""),
                 o.get("classification", ""), o.get("creditline", ""),
                 row.get("uuid", ""), row.get("iiifurl", ""),
                 row.get("iiifthumburl", ""), row.get("assistivetext", "")))
            n += 1
            if n % 20000 == 0:
                print(f"  {n} images joined...", flush=True)
    con.commit()
    print(f"  {n} open-access images", flush=True)
    print("creating full-text index...", flush=True)
    try:
        cur.execute("CREATE VIRTUAL TABLE nga_fts USING fts5(title, artist, medium, class, assist, "
                    "content='nga', content_rowid='rowid')")
        cur.execute("INSERT INTO nga_fts(rowid, title, artist, medium, class, assist) "
                    "SELECT rowid, title, artist, medium, class, assist FROM nga")
        con.commit()
        print("  FTS5 index ready", flush=True)
    except sqlite3.OperationalError as e:
        print(f"  FTS5 unavailable ({e}); LIKE search will be used", flush=True)
    con.close()
    print(f"DONE -> {db_path} ({os.path.getsize(db_path) // 1048576}MB)", flush=True)

if __name__ == "__main__":
    build()
