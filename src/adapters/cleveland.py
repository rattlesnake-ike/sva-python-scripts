"""Cleveland adapter (https://www.clevelandart.org/open-access-api — keyless,
CC0: 64k records, 37k images). Native created_after/created_before year facet
from the brief; faithful-first order (dated, then plain).

Image tiers: web (~600px, fast grid+lightbox) / print (~2300px, drag-in+PSD).
The full .tif masters (often 50MB+) are never fetched.
"""
from validator import brief_range, clean_query

from .http import get

API = "https://openaccess-api.clevelandart.org/api/artworks"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}

def _creator(artists):
    if not artists:
        return ""
    names = []
    for a in artists:
        if isinstance(a, dict):
            names.append(a.get("name") or a.get("display_name") or "")
        else:
            names.append(str(a))
    return ", ".join(n for n in names if n)[:80]

def _to_item(a):
    imgs = a.get("images") or {}
    web = (imgs.get("web") or {}).get("url") or ""
    prt = (imgs.get("print") or {}).get("url") or ""
    return {
        "id": f"cma-{a.get('id')}",
        "title": a.get("title") or "(untitled)",
        "date_str": a.get("creation_date") or "",
        "creator": _creator(a.get("artists")),
        "source": "Cleveland/" + str(a.get("department") or "collection"),
        "image_url": prt or web,
        "thumb_url": web or prt,
        "large_url": web or prt,
        "page_url": a.get("url") or "",
        "medium": a.get("type") or "",
        "extra": " | ".join(s for s in [a.get("technique"), a.get("creditline"),
                                        "CC0 open access"] if s)[:140],
    }

def _fetch(params, limit):
    r = get(API, params=params, headers=UA, timeout=25)
    r.raise_for_status()
    items = []
    for a in (r.json().get("data") or []):
        it = _to_item(a)
        if it["thumb_url"] or it["image_url"]:
            items.append(it)
        if len(items) >= limit:
            break
    return items

def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    plans = []
    if rng:
        plans.append({"q": q, "limit": 30, "has_image": 1,
                      "created_after": rng[0], "created_before": rng[1]})
    plans.append({"q": q, "limit": 30, "has_image": 1})
    last_err = None
    for i, params in enumerate(plans):
        try:
            items = _fetch(params, limit)
            if items:
                if i:
                    for it in items:
                        it["extra"] = (it["extra"] + " | via unfiltered search").strip()
                return items, None
            last_err = f"Cleveland: 0 hits for '{q}'" + (" (dated)" if i == 0 else "")
        except Exception as e:
            last_err = f"Cleveland: {str(e)[:130]}"
    return [], last_err or "Cleveland: no results"
