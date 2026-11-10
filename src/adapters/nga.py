"""NGA adapter — real search over the Gallery's CC0 open-data dump (no NGA search
API exists, so we bring the data home instead).

Setup (once):  python nga_build.py     (~170MB download, builds data/nga.sqlite)
Searches 60k+ open-access works by keyword (title/artist/medium/assistive text)
with brief year-range overlap, emitting IIIF URLs + object-page links.

Without the local DB it falls back to 3 verified IIIF samples (flagged).
"""
import os
import re
import sqlite3

from validator import brief_range

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "..", "data", "nga.sqlite")
SEARCH_URL = "https://www.nga.gov/artwork-search?download=1"

# Verified 2026-10-14 fallback samples (IIIF HTTP 200, CC0).
SAMPLES = [
    {"objectid": "61379",
     "title": "Woman with a Parasol — Madame Monet and Her Son",
     "displaydate": "1875", "artist": "Claude Monet",
     "uuid": "99758d9d-c10b-4d02-a198-7e49afb1f3a6",
     "medium": "Painting",
     "credit": "National Gallery of Art, Collection of Mr. and Mrs. Paul Mellon (open access, CC0)"},
    {"objectid": "bazille-peonies",
     "title": "Young Woman with Peonies",
     "displaydate": "1870", "artist": "Frédéric Bazille",
     "uuid": "2c964e55-3f80-43c3-a581-1d7a276b6d0f",
     "medium": "Painting",
     "credit": "National Gallery of Art, open access (CC0)",
     "page": "https://www.nga.gov/artwork-search?download=1&keywords=bazille+peonies"},
    {"objectid": "507",
     "title": "Ginevra de' Benci",
     "displaydate": "c. 1474/1478", "artist": "Leonardo da Vinci",
     "uuid": "8f29e3c9-a289-4d53-abf0-31a66e9e98fa",
     "medium": "Painting",
     "credit": "National Gallery of Art, Ailsa Mellon Bruce Fund (open access, CC0)"},
]

def _iiif(uuid_or_url, w=800):
    base = uuid_or_url if uuid_or_url.startswith("http") else f"https://api.nga.gov/iiif/{uuid_or_url}"
    return f"{base}/full/!{w},{w}/0/default.jpg"

def _sample_items(query, limit):
    toks = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    ranked = []
    for s in SAMPLES:
        hay = (s["title"] + " " + s["artist"] + " " + s["displaydate"]).lower()
        ranked.append((sum(1 for t in toks if t in hay), s))
    ranked.sort(reverse=True, key=lambda x: x[0])
    items = []
    for score, s in ranked[:limit]:
        items.append({
            "id": f"nga-{s['objectid']}",
            "title": s["title"],
            "date_str": s["displaydate"],
            "creator": s["artist"],
            "source": "NGA",
            "image_url": _iiif(s["uuid"]),
            "thumb_url": _iiif(s["uuid"], 400),
            "page_url": s.get("page") or f"https://www.nga.gov/artworks/{s['objectid']}",
            "medium": s["medium"],
            "extra": s["credit"] + (" | token-match" if score > 0
                    else f" | curated sample — expand by hand: {SEARCH_URL}"),
        })
    return items

def _tokens(query):
    toks = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:5]

def _row_to_item(r):
    (oid, title, ddate, by, ey, artist, medium, cls, credit, uuid, iiif, thumb, assist) = r
    date_str = ddate or (str(by) if by else "")
    return {
        "id": f"nga-{oid}",
        "title": title or "(untitled)",
        "date_str": date_str,
        "creator": artist or "",
        "source": "NGA",
        "image_url": _iiif(iiif or uuid),
        "thumb_url": thumb or _iiif(iiif or uuid, 400),
        "page_url": f"https://www.nga.gov/artworks/{oid}",
        "medium": (cls or medium or "").strip() or "Artwork",
        "extra": (credit or "National Gallery of Art, open access (CC0)"),
    }

COLS = ("objectid,title,displaydate,beginyear,endyear,artist,medium,"
        "class,credit,uuid,iiif,iiifthumb,assist")
QCOLS = ", ".join(f"nga.{c}" for c in COLS.split(","))

def query_db(db_path, query, limit=6, year_range=None):
    """Search the local NGA sqlite. Returns (items, used_fts). Raises on no DB."""
    toks = _tokens(query)
    if not toks:
        return [], False
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    has_fts = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='nga_fts'").fetchone()
    dated = [f"beginyear<={year_range[1]} AND endyear>={year_range[0]}"] if year_range else []
    items = []
    if has_fts:
        match = " ".join(f'"{t}"' for t in toks)
        base = (f"SELECT {QCOLS} FROM nga JOIN nga_fts ON nga.rowid=nga_fts.rowid "
                f"WHERE nga_fts MATCH ?")
        passes = [dated + ["beginyear>0"], ["beginyear=0"]] if year_range else [[]]
        seen = set()  # O(1) dedupe across the dated/undated passes
        for conds in passes:
            args = [match]
            sql = base + (" AND " + " AND ".join(conds) if conds else "") + " LIMIT ?"
            for r in cur.execute(sql, args + [limit]).fetchall():
                if len(items) >= limit:
                    break
                if r[0] not in seen:
                    seen.add(r[0])
                    items.append(_row_to_item(r))
            if len(items) >= limit:
                break
        con.close()
        return items, True
    # LIKE fallback (no FTS5)
    cond = " AND ".join(
        "(title LIKE ? OR artist LIKE ? OR medium LIKE ? OR class LIKE ? OR assist LIKE ?)"
        for _ in toks)
    args = []
    for t in toks:
        args += [f"%{t}%"] * 5
    sql = f"SELECT {COLS} FROM nga WHERE {cond}"
    if dated:
        rows = cur.execute(sql + " AND " + dated[0] + " LIMIT ?", args + [limit]).fetchall()
        items = [_row_to_item(r) for r in rows]
    if len(items) < limit:
        rows = cur.execute(sql + " LIMIT ?", args + [limit]).fetchall()
        seen = {i["id"] for i in items}
        for r in rows:
            it = _row_to_item(r)
            if it["id"] not in seen and len(items) < limit:
                items.append(it)
                seen.add(it["id"])
    con.close()
    return items, False

def search(query, limit=6, brief=None):
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    if os.path.exists(DB):
        try:
            items, _fts = query_db(DB, query, limit, rng)
            if items:
                return items, None
            return [], f"NGA: 0 local hits for '{query}' (60k+ open-access works indexed)"
        except Exception as e:
            return _sample_items(query, limit), f"NGA: local index error ({e}); showing verified samples"
    return _sample_items(query, limit), \
        "NGA: local index missing — run python nga_build.py once for real search (showing verified samples)"
