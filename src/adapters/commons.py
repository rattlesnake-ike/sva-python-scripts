"""Commons adapter (https://commons.wikimedia.org/wiki/Commons:API — MediaWiki
Action API, keyless). All files are freely licensed with attribution.

Two requests per search: generator=search (site relevance order, bitmap files
only) + one batched revisions call for wikitext. Artwork dates come from the
file's |date= field, filename, or filtered categories — NEVER the upload
DateTime (verified: a 1475 painting reports DateTime 2024). Unresolvable dates
stay empty and the validator marks them '?', same as the sites show 'date
unknown'. Attribution (artist/license/page) rides in every card.
"""
import html as _html
import re

from validator import clean_query

from .http import get

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}
YEAR = r"(1[0-9]{3}|20[0-2][0-9])"
SKIP_CAT = re.compile(r"photograph|taken on|quality|valued|upload|user:|wikimedian|by \w+$", re.I)
GENRE_CAT = re.compile(r"painting|portrait|drawing|print|sculpture|photograph|work|art\b", re.I)

def _strip(raw):
    return _html.unescape(re.sub(r"<[^>]+>", " ", raw or "")).strip(" :;,-")

def _meta(ext, key):
    return _strip((ext.get(key) or {}).get("value"))

def artwork_date(title, wikitext):
    """Best-effort artwork year: |date= field, filename, then clean categories."""
    m = re.search(r"\|[Dd]ate\s*=\s*(.{0,140})", wikitext)
    if m and "photo date" not in wikitext[max(0, m.start() - 30):m.start()].lower():
        years = re.findall(YEAR, m.group(1))
        # drop EXIF-style stamps inside the field
        years = [y for y in years if not re.search(rf"{y}-[01]\d-[0-3]\d", m.group(1))]
        if years:
            return years[0]
    years = re.findall(YEAR, title)
    if years:
        return years[0]
    cands, genre = [], []
    for cat in re.findall(r"\[\[Category:([^\]]+)\]\]", wikitext):
        if SKIP_CAT.search(cat):
            continue
        for y in re.findall(YEAR, cat):
            (genre if GENRE_CAT.search(cat) else cands).append(y)
    return (genre + cands or [""])[0]

def _medium(ext, wikitext):
    obj = _meta(ext, "ObjectName").lower()
    if "paint" in obj:
        return "Painting"
    if "photo" in obj or "daguerreotype" in obj:
        return "Photograph"
    if obj and ("print" in obj or "drawing" in obj):
        return obj.title()[:24]
    for cat in re.findall(r"\[\[Category:([^\]]+)\]\]", wikitext):
        if re.search(r"paintings\b", cat, re.I) and not SKIP_CAT.search(cat):
            return "Painting"
    return "Artwork"

def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    try:
        r = get(API, params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
            "gsrlimit": min(max(limit * 2 + 2, 6), 20),
            "prop": "imageinfo", "iiprop": "url|size|extmetadata",
            "iiurlwidth": 800,
        }, headers=UA, timeout=25)
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
        if not pages:
            return [], f"Commons: 0 hits for '{q}' (try broader terms)"
        # one batched call for wikitext dates
        titles = "|".join(p.get("title", "") for p in pages.values() if p.get("title"))
        wt = {}
        try:
            r2 = get(API, params={
                "action": "query", "format": "json", "prop": "revisions",
                "rvprop": "content", "rvslots": "main", "titles": titles,
            }, headers=UA, timeout=25)
            r2.raise_for_status()
            for p in (r2.json().get("query") or {}).get("pages", {}).values():
                revs = p.get("revisions") or []
                wt[p.get("title", "")] = (((revs or [{}])[0].get("slots") or {}).get("main") or {}).get("*", "")
        except Exception:
            pass
        items = []
        for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
            if len(items) >= limit:
                break
            title = p.get("title", "")
            ii = (p.get("imageinfo") or [{}])[0]
            ext = ii.get("extmetadata") or {}
            text = wt.get(title, "")
            artist = _meta(ext, "Artist")
            lic = _meta(ext, "LicenseShortName") or "freely licensed (see page)"
            items.append({
                "id": "wc-" + re.sub(r"\W+", "_", title)[:40],
                "title": title.replace("File:", "").rsplit(".", 1)[0][:90],
                "date_str": artwork_date(title, text),
                "creator": artist[:60],
                "source": "Commons",
                "image_url": (ii.get("url") or "").split("?")[0],
                "thumb_url": (ii.get("thumburl") or ii.get("url") or "").split("?")[0],
                "large_url": (ii.get("thumburl") or ii.get("url") or "").split("?")[0],
                "page_url": ii.get("descriptionurl") or "",
                "medium": _medium(ext, text),
                "extra": f"{artist[:60]} | {lic[:40]}".strip(" |"),
            })
        items = [it for it in items if it["image_url"] or it["thumb_url"]]
        if not items:
            return [], "Commons: hits had no downloadable image"
        return items, None
    except Exception as e:
        return [], f"Commons: {str(e)[:150]}"
