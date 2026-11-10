"""Minneapolis Institute of Art (Mia) adapter — keyless search API.

Mia exposes a simple search endpoint at search.artsmia.org and an image CDN at
img.artsmia.org. Only records with an explicit ``rights_type`` of
``Public Domain``, a full-display rights setting, a valid image, and a dated
object are returned. ``In Copyright``, ``Unknown``, and limited-display records
are skipped — there is no "maybe" path.

Image tiers are the museum's own CDN: 400px preview, 800px web tier, and the
full public-domain JPEG for drag-in. The full file is used only where Mia
marks the record as public domain + full display.
"""
import re
from urllib.parse import quote

from validator import brief_range, clean_query, parse_years

from .http import get

API = "https://search.artsmia.org/"
CDN = "https://img.artsmia.org/web_objects_cache/"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokens(query):
    return [t for t in re.findall(r"[a-z0-9]+", _clean(query).lower()) if len(t) > 1]


def _matches(record, tokens):
    """Keep a record only when the query appears in object metadata.

    Mia's search endpoint also matches long catalogue notes, which can surface
    unrelated objects for a short word like ``bar``. Matching the title,
    object name, medium, artist, classification and department keeps the
    retrieval focused without pretending the API is a semantic search.
    """
    if not tokens:
        return True
    text = " ".join(_clean(record.get(field)).lower() for field in (
        "title", "object_name", "medium", "artist", "classification", "department"
    ))
    return any(re.search(r"\b" + re.escape(token) + r"\b", text) for token in tokens)


def _date_score(date_str, rng):
    if not rng:
        return 1
    years = parse_years(date_str)
    if not years:
        return 2
    if len(years) > 1 and max(years) - min(years) > 80:
        return 1
    lo, hi = rng
    return 0 if any(lo <= year <= hi for year in years) else 1


def _cdn_urls(record):
    location = _clean(record.get("Cache_Location")).replace("\\", "/").strip("/")
    rendition = _clean(record.get("Primary_RenditionNumber"))
    rendition = re.sub(r"\.jpg$", "", rendition, flags=re.I)
    if not location or not rendition:
        return "", "", ""
    base = f"{CDN}{location}/{rendition}"
    return base + "_400.jpg", base + "_800.jpg", base + "_full.jpg"


def _is_public_domain(record):
    """Strict triage: PD status, full display, valid image, and a date."""
    if _clean(record.get("rights_type")).lower() != "public domain":
        return False
    if _clean(record.get("image")).lower() != "valid":
        return False
    if _clean(record.get("Rights_Image_Display")).lower() != "full":
        return False
    if not _clean(record.get("dated")):
        return False
    if not _clean(record.get("Cache_Location")):
        return False
    if not _clean(record.get("Primary_RenditionNumber")):
        return False
    return True


def _title(record):
    return _clean(record.get("title")) or "(untitled)"


def _creator(record):
    artist = _clean(record.get("artist"))
    if artist:
        return artist[:80]
    return ""


def _medium(record):
    return (_clean(record.get("medium")) or _clean(record.get("object_name")) or "")[:80]


def _to_item(record):
    thumb, web, full = _cdn_urls(record)
    page = f"https://collections.artsmia.org/art/{record.get('id')}"
    extra = "Public domain (CC PDM) | Mia"
    credit = _clean(record.get("creditline"))
    if credit:
        extra += " | " + credit[:100]
    return {
        "id": "mia-" + str(record.get("id")),
        "title": _title(record),
        "date_str": _clean(record.get("dated")),
        "creator": _creator(record),
        "source": "Mia/" + (_clean(record.get("department")) or "collection"),
        "image_url": full or web or thumb,
        "thumb_url": thumb or web or full,
        "large_url": full or web or thumb,
        "page_url": page,
        "medium": _medium(record),
        "extra": extra,
    }


def _fetch(query, limit, tokens=None, brief=None):
    url = API + quote(query, safe="")
    r = get(url, params={"size": 100}, headers=UA, timeout=25)
    r.raise_for_status()
    data = r.json()
    items = []
    for hit in (data.get("hits") or {}).get("hits") or []:
        record = hit.get("_source") if isinstance(hit, dict) else None
        if not isinstance(record, dict) or not _is_public_domain(record):
            continue
        if not _matches(record, tokens or []):
            continue
        item = _to_item(record)
        if not item["image_url"]:
            continue
        items.append(item)
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    items.sort(key=lambda item: _date_score(item["date_str"], rng))
    return items[:limit]


def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    plans = [q]
    words = q.split()
    if len(words) > 1:
        core = words[0]
        if core and core != q:
            plans.append(core)

    items, seen, last_err = [], set(), None
    for i, plan in enumerate(plans):
        try:
            found = _fetch(plan, limit, _tokens(plan), brief)
        except Exception as e:
            last_err = f"Mia: {str(e)[:130]}"
            continue
        for item in found:
            item_id = item.get("id")
            if item_id in seen:
                continue
            seen.add(item_id)
            if i:
                item["extra"] = (item["extra"] + " | via broader search").strip()
            items.append(item)
        if found:
            last_err = None
        elif last_err is None:
            last_err = f"Mia: 0 public-domain image hits for '{plan}'"
        if len(items) >= limit * 2:
            break

    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    items.sort(key=lambda item: _date_score(item["date_str"], rng))
    return items[:limit], last_err
