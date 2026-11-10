"""Wellcome adapter (https://api.wellcomecollection.org — keyless catalogue API).

Historical photos/drawings with production dates and per-record IIIF + license.
Rights are mixed, so only public-domain-marked records are kept (thumbnail
license id pdm/cc0); the API has no usable license/date facet, so the query is
the faithful site query and the validator judges dates — dated-overlap hits
rank first, undated fill after.
"""
import re

from validator import brief_range, clean_query, parse_years

from .http import get

API = "https://api.wellcomecollection.org/catalogue/v2/works"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}
PD = {"pdm", "cc0", "public-domain", "public domain"}

def _thumb(w):
    t = w.get("thumbnail") or {}
    return t.get("url") or "", ((t.get("license") or {}).get("id") or "").lower()

def _bigger(url, width):
    if "/full/" in url:
        return re.sub(r"/full/[^/]*/", f"/full/{width},/", url, count=1)
    return url

def _date(w):
    for p in w.get("production") or []:
        ds = p.get("dates") or []
        if ds and ds[0].get("label"):
            return str(ds[0]["label"])
        if p.get("label"):
            return str(p["label"])
    return ""

def _medium(w):
    phys = (w.get("physicalDescription") or "").lower()
    title = (w.get("title") or "").lower()
    hay = phys + " " + title
    if ("book" in phys or "bound" in phys
            or re.search(r"\b\d+\s*pp?\b|\bpages?\b|\bvols?\b", phys)):
        return "Book/Text"
    if "paint" in hay:
        return "Painting"
    if "photo" in hay or "daguerreotype" in hay or "snapshot" in hay:
        return "Photograph"
    if "draw" in hay or "etch" in hay or "print" in hay or "sketch" in hay:
        core = re.sub(r"^[\d\s]+", "", phys.split(":")[0]).strip().title()[:28]
        return core or "Drawing"
    return "Artwork"

def _to_item(w):
    thumb, lic = _thumb(w)
    contribs = []
    for c in w.get("contributors") or []:
        ag = c.get("agent") or {}
        if ag.get("label"):
            contribs.append(ag["label"])
    lic_lbl = ""
    try:
        lic_lbl = (w.get("thumbnail") or {}).get("license", {}).get("label", "")
    except Exception:
        pass
    return {
        "id": "wl-" + str(w.get("id")),
        "title": (w.get("title") or "(untitled)")[:90],
        "date_str": _date(w),
        "creator": ", ".join(contribs)[:80],
        "source": "Wellcome",
        "image_url": _bigger(thumb, 1000),
        "thumb_url": thumb,
        "large_url": _bigger(thumb, 800),
        "page_url": f"https://wellcomecollection.org/works/{w.get('id')}",
        "medium": _medium(w),
        "extra": " | ".join(s for s in [", ".join(contribs)[:60], lic_lbl, "public domain"] if s)[:140],
    }

def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    try:
        cands = []
        for page in (1, 2):  # two result pages: PD-marked records are sparse
            r = get(API, params={"query": q, "pageSize": 40, "page": page},
                    headers=UA, timeout=25)
            r.raise_for_status()
            for w in (r.json().get("results") or []):
                thumb, lic = _thumb(w)
                if not thumb or lic not in PD:
                    continue
                cands.append(_to_item(w))
            if len(cands) >= limit * 2:
                break
        if not cands:
            return [], f"Wellcome: 0 public-domain hits for '{q}' (in-copyright records excluded)"
        if rng:
            dated = [it for it in cands
                     if any(rng[0] <= y <= rng[1] for y in parse_years(it["date_str"]))]
            rest = [it for it in cands if it not in dated]
            return (dated + rest)[:limit], None
        return cands[:limit], None
    except Exception as e:
        return [], f"Wellcome: {str(e)[:150]}"
