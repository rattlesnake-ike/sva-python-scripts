"""Harvard adapter (https://api.harvardartmuseums.org — keyed REST, ~250k
records). GET /object mirrors the site's facets: keyword full-text plus a
native yearmade=lo-hi range from the brief (verified working 2026-10-16),
faithful-first order (dated, then plain).

Key: env HARVARD_API_KEY or local .harvard_key file.
Images via IIIF: 400px grid tier, 843px lightbox tier, full-res drag-in tier.
Records with imagepermissionlevel 2 (do-not-display) or no image URL are
skipped — every hit is downloadable and openly viewable.
"""
import os

from validator import brief_range, clean_query

from .http import get

API = "https://api.harvardartmuseums.org/object"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}
FIELDS = ("objectid,title,dated,datebegin,dateend,people,classification,"
          "medium,technique,primaryimageurl,images,url,creditline,"
          "imagepermissionlevel,accesslevel,department,division,culture")


def _key():
    k = (os.environ.get("HARVARD_API_KEY") or "").strip()
    if k:
        return k
    try:  # local key file (written once, no need to set env every run)
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", ".harvard_key"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _creator(people):
    names = []
    for p in people or []:
        if isinstance(p, dict):
            names.append(p.get("displayname") or p.get("name") or "")
        else:
            names.append(str(p))
    return ", ".join(n for n in names if n)[:80]


def _base(rec):
    imgs = rec.get("images") or []
    for im in sorted(imgs, key=lambda m: (m or {}).get("displayorder") or 99):
        b = (im or {}).get("baseimageurl") or ""
        if b:
            return b.rstrip("/")
    return (rec.get("primaryimageurl") or "").rstrip("/")


def _to_item(r):
    base = _base(r)
    people = _creator(r.get("people"))
    medium = r.get("medium") or r.get("classification") or ""
    dept = r.get("department") or r.get("division") or "collection"
    extra = " | ".join(s for s in [r.get("creditline"), r.get("culture"),
                                   "Harvard Art Museums"] if s)[:140]
    return {
        "id": f"harv-{r.get('objectid')}",
        "title": r.get("title") or "(untitled)",
        "date_str": r.get("dated") or "",
        "creator": people,
        "source": "Harvard/" + str(dept),
        "image_url": f"{base}/full/full/0/default.jpg" if base else "",
        "thumb_url": f"{base}/full/400,/0/default.jpg" if base else "",
        "large_url": f"{base}/full/843,/0/default.jpg" if base else "",
        "page_url": r.get("url") or "",
        "medium": medium,
        "extra": extra,
    }


def _keep(r):
    # imagepermissionlevel 2 = do not display any images; 0/1 are viewable
    # (level 1 caps at 256px on their site, but IIIF 400px thumbs still load).
    if r.get("imagepermissionlevel") == 2:
        return False
    if r.get("accesslevel") == 0:
        return False
    return bool(_base(r))


def _fetch(params, limit):
    r = get(API, params=params, headers=UA, timeout=25)
    if r.status_code in (401, 403):
        raise RuntimeError("key rejected (401/403) — check HARVARD_API_KEY.")
    r.raise_for_status()
    items = []
    for rec in (r.json().get("records") or []):
        if not _keep(rec):
            continue
        items.append(_to_item(rec))
        if len(items) >= limit:
            break
    return items


def search(query, limit=6, brief=None):
    key = _key()
    if not key:
        return [], ("Harvard: no API key. Free key (1 min signup): "
                    "https://docs.google.com/forms/d/1Fe1H4nOhFkrLpaeBpLAnSrIMYvcAxnYWm0IU9a6IkFA/viewform "
                    "then set HARVARD_API_KEY and search again.")
    q = clean_query(query) or query
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    plans = []
    if rng:
        plans.append({"keyword": q, "yearmade": f"{rng[0]}-{rng[1]}"})
    plans.append({"keyword": q})
    last_err = None
    for i, plan in enumerate(plans):
        params = {"apikey": key, "hasimage": 1,
                  "size": max(10, min(limit * 3, 100)),
                  "fields": FIELDS, **plan}
        try:
            items = _fetch(params, limit)
            if items:
                if i:
                    for it in items:
                        it["extra"] = (it["extra"] + " | via unfiltered search").strip()
                return items, None
            tag = " (dated)" if i == 0 and rng else ""
            last_err = f"Harvard: 0 hits for '{q}'{tag}"
        except Exception as e:
            last_err = f"Harvard: {str(e)[:130]}"
    return [], last_err or "Harvard: no results"
