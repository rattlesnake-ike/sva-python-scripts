"""Met adapter (https://metmuseum.github.io — Collection API, keyless, 80 req/s).

Two-step: v1.1/search (paginated IDs; v1 retired Oct 1 2026) with hasImages +
native dateBegin/dateEnd from the brief, then object records fetched in parallel.
Records carry machine dates (objectBeginDate/EndDate), hi-res public-domain
images, and department/medium — all verifiable, satisfying the dated-sources rule.
"""
from concurrent.futures import ThreadPoolExecutor

from validator import brief_range, clean_query

from .http import get

SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}

def _to_item(o):
    pd = bool(o.get("isPublicDomain"))
    cls = (o.get("classification") or "").strip()
    return {
        "id": f"met-{o.get('objectID')}",
        "title": o.get("title") or "(untitled)",
        "date_str": o.get("objectDate") or "",
        "creator": o.get("artistDisplayName") or "",
        "source": "Met/" + str(o.get("department") or "collection"),
        "image_url": o.get("primaryImage") or o.get("primaryImageSmall") or "",
        "thumb_url": o.get("primaryImageSmall") or o.get("primaryImage") or "",
        # speed tier for the lightbox: web-large (~1MB) now, original upgrades in
        "large_url": o.get("primaryImageSmall") or o.get("primaryImage") or "",
        "page_url": o.get("objectURL") or "",
        "medium": cls or o.get("objectName") or "",
        "extra": (o.get("creditLine") or "")
                 + (" | public domain" if pd else " | check rights: " + str(o.get("rightsAndReproduction") or "in copyright?")),
        "_begin": o.get("objectBeginDate") or 0,
        "_end": o.get("objectEndDate") or 0,
    }

def _get_object(oid):
    try:
        r = get(OBJECT + str(oid), headers=UA, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    loc = " ".join(w for w in str((brief or {}).get("location", "")).replace(",", " ").split()
                   if len(w) > 2)
    # Faithful first: user's keywords + period facet (the site's date filter),
    # then highlights (famous, imaged, usually PD), then +geo facet, then plain.
    plans = []
    if rng:
        plans.append(("period", {"q": q, "hasImages": "true", "dateBegin": rng[0],
                                 "dateEnd": rng[1]}))
    plans.append(("highlights", {"q": q, "hasImages": "true", "isHighlight": "true"}))
    if rng and loc:
        plans.append(("period+geo", {"q": q, "hasImages": "true", "dateBegin": rng[0],
                                     "dateEnd": rng[1], "geoLocation": loc.title()}))
    plans.append(("plain", {"q": q, "hasImages": "true"}))
    ids, last_err, won = [], None, "period"
    for desc, params in plans:
        try:
            r = get(SEARCH, params=dict(params, limit=100), headers=UA, timeout=20)
            r.raise_for_status()
            data = r.json()
            ids = data.get("objectIDs") or []
            if ids:
                won = desc
                break
            last_err = f"Met: 0 hits for { {k: v for k, v in params.items() if k != 'limit'} }"
        except Exception as e:
            last_err = f"Met: {str(e)[:120]}"
    if not ids:
        return [], last_err or "Met: no results"
    # hasImages matches internal holdings, but image URLs are only served for
    # public-domain works (verified: ~10% servable) — scan the ID page in
    # parallel until the grid fills (max 60 record fetches).
    with ThreadPoolExecutor(max_workers=8) as pool:
        scanned = [o for o in pool.map(_get_object, ids[:60]) if o]
    objs = [o for o in scanned
            if o.get("primaryImage") or o.get("primaryImageSmall")]
    items = []
    for o in objs:
        if not (o.get("primaryImage") or o.get("primaryImageSmall")):
            continue
        it = _to_item(o)
        if won != "period":
            it["extra"] = (it["extra"] + f" | via {won} search").strip(" |")
        items.append(it)
        if len(items) >= limit:
            break
    # public-domain first (open-use ethos), stable otherwise
    items.sort(key=lambda it: 0 if "public domain" in it["extra"] else 1)
    if not items:
        return [], f"Met: {len(objs)} records had no downloadable image"
    return items[:limit], None
