"""AIC adapter (https://www.artic.edu/open-access/public-api — keyless REST,
50k+ public-domain/CC0 works with images). GET search mirrors the site's
facets: full-text q plus a same-field date_start range (the API accepts only
one query[...] clause per GET, so is_public_domain is enforced client-side).

Images via IIIF: 400px grid/lightbox tier, 1686px drag-in tier.
"""
from validator import brief_range, clean_query

from .http import get

API = "https://api.artic.edu/api/v1/artworks/search"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}
FIELDS = ("id,title,artist_display,date_display,date_start,date_end,image_id,"
          "thumbnail,medium_display,department_title,credit_line,is_public_domain")

def _to_item(a):
    iid = a.get("image_id") or ""
    return {
        "id": f"aic-{a.get('id')}",
        "title": a.get("title") or "(untitled)",
        "date_str": a.get("date_display") or "",
        "creator": a.get("artist_display") or "",
        "source": "AIC/" + str(a.get("department_title") or "collection"),
        "image_url": f"https://www.artic.edu/iiif/2/{iid}/full/1686,/0/default.jpg" if iid else "",
        "thumb_url": f"https://www.artic.edu/iiif/2/{iid}/full/400,/0/default.jpg" if iid else "",
        "large_url": f"https://www.artic.edu/iiif/2/{iid}/full/843,/0/default.jpg" if iid else "",
        "page_url": f"https://www.artic.edu/artworks/{a.get('id')}",
        "medium": a.get("medium_display") or "",
        "extra": ((a.get("credit_line") or "") + " | CC0 public domain").strip(" |")[:140],
    }

def _keep(a):
    # PD enforced client-side (API takes one query[...] clause per GET):
    # drop explicitly non-PD records; imageless ones go too
    return a.get("is_public_domain") is not False and bool(a.get("image_id"))

def _fetch(params, limit):
    r = get(API, params=params, headers=UA, timeout=25)
    r.raise_for_status()
    items = []
    for a in (r.json().get("data") or []):
        if not _keep(a):
            continue
        items.append(_to_item(a))
        if len(items) >= limit:
            break
    return items

def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    base = {"q": q, "limit": 30, "fields": FIELDS}
    plans = []
    if rng:
        plans.append(dict(base, **{"query[range][date_start][gte]": rng[0],
                                   "query[range][date_start][lte]": rng[1]}))
    plans.append(dict(base))
    last_err = None
    for i, params in enumerate(plans):
        try:
            items = _fetch(params, limit)
            if items:
                if i:
                    for it in items:
                        it["extra"] = (it["extra"] + " | via unfiltered search").strip()
                return items, None
            last_err = f"AIC: 0 PD hits for '{q}'" + (" (dated)" if i == 0 else "")
        except Exception as e:
            last_err = f"AIC: {str(e)[:130]}"
    return [], last_err or "AIC: no results"
