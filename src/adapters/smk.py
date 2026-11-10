"""SMK adapter (https://api.smk.dk/api/v1/art/search/ — keyless).

Statens Museum for Kunst (SMK) publishes its collection through an open API.
Only records that are explicitly public domain are returned: the API record
must carry ``public_domain: true`` AND a Creative Commons Public Domain Mark /
CC0 rights URL. Records with an image but no PD flag, or a PD flag but no PD
rights URL, are skipped. A production date is required too, because this tool
only trusts dated sources.

Images use SMK's IIIF server: an 843px preview and a 1600px drag-in tier.
The full ``image_native`` file can be many megabytes, so it is only a fallback
for records whose IIIF id is missing.
"""
import re

from validator import brief_range, clean_query, parse_years

from .http import get

API = "https://api.smk.dk/api/v1/art/search/"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}
PD_FILTER = "[public_domain:true],[has_image:true]"
PD_RIGHTS = ("https://creativecommons.org/publicdomain/",
             "http://creativecommons.org/publicdomain/")


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _date(record):
    """Return the museum's production date(s), never a file/upload date."""
    out = []
    dates = record.get("production_date") or []
    if isinstance(dates, dict):
        dates = [dates]
    for item in dates:
        if not isinstance(item, dict):
            continue
        period = _clean(item.get("period"))
        if period:
            out.append(period)
            continue
        start = _clean(item.get("start"))[:4]
        end = _clean(item.get("end"))[:4]
        if start and end and start != end:
            out.append(f"{start}-{end}")
        elif start:
            out.append(start)
    return ", ".join(dict.fromkeys(out))[:80]


def _date_score(date_str, rng):
    """Prefer objects inside the brief range; broad API results can put a
    17th-century portrait ahead of the 1890s one the brief asked for."""
    if not rng:
        return 1
    years = parse_years(date_str)
    if not years:
        return 2
    # A very wide range (e.g. "1592-1890") is usually an artist/life span, not
    # a usable production date; do not let its endpoint jump the queue.
    if len(years) > 1 and max(years) - min(years) > 80:
        return 1
    lo, hi = rng
    return 0 if any(lo <= year <= hi for year in years) else 1


def _creator(record):
    out = []
    for production in record.get("production") or []:
        if not isinstance(production, dict):
            continue
        name = _clean(production.get("creator"))
        if name and name.lower() not in ("ubekendt", "unknown", "anonymous"):
            out.append(name)
    return ", ".join(dict.fromkeys(out))[:80]


def _title(record):
    for title in record.get("titles") or []:
        if isinstance(title, dict) and title.get("title"):
            return _clean(title["title"])
    return "(untitled)"


def _medium(record):
    out = []
    for obj in record.get("object_names") or []:
        if isinstance(obj, dict) and obj.get("name"):
            out.append(_clean(obj["name"]))
    for technique in record.get("techniques") or []:
        if technique:
            out.append(_clean(technique))
    return " / ".join(dict.fromkeys(out))[:80]


def _image_urls(record):
    """(thumb, full) from IIIF; fall back to SMK's thumbnail/download files."""
    base = _clean(record.get("image_iiif_id"))
    if not base:
        info = _clean(record.get("image_iiif_info"))
        if info.endswith("/info.json"):
            base = info[:-len("/info.json")]
    if base:
        return (f"{base}/full/!843,843/0/default.jpg",
                f"{base}/full/!1600,1600/0/default.jpg")
    thumb = _clean(record.get("image_thumbnail")) or _clean(record.get("image_native"))
    full = _clean(record.get("image_native")) or thumb
    return thumb, full


def _is_public_domain(record):
    """Both flags are required; a PD-looking image without the rights URL is
    not enough. This deliberately rejects mixed-rights records."""
    if record.get("public_domain") is not True:
        return False
    rights = _clean(record.get("rights")).lower()
    return rights.startswith(PD_RIGHTS)


def _to_item(record):
    object_number = _clean(record.get("object_number")) or _clean(record.get("id"))
    thumb, full = _image_urls(record)
    return {
        "id": "smk-" + object_number,
        "title": _title(record),
        "date_str": _date(record),
        "creator": _creator(record),
        "source": "SMK/National Gallery of Denmark",
        "image_url": full,
        "thumb_url": thumb,
        "large_url": full,
        "page_url": _clean(record.get("frontend_url"))
                    or f"https://open.smk.dk/artwork/image/{object_number}",
        "medium": _medium(record),
        "extra": "Public domain (CC PDM) | SMK",
    }


def _fetch(query, limit, brief=None):
    r = get(API, params={
        "keys": query,
        "offset": 0,
        "rows": 100,
        "lang": "en",
        "filters": PD_FILTER,
    }, headers=UA, timeout=30)
    r.raise_for_status()
    data = r.json()
    items = []
    for record in data.get("items") or []:
        if not _is_public_domain(record) or not record.get("has_image"):
            continue
        if not _date(record):
            continue
        thumb, full = _image_urls(record)
        if not full:
            continue
        items.append(_to_item(record))
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
            found = _fetch(plan, limit, brief)
        except Exception as e:
            last_err = f"SMK: {str(e)[:130]}"
            continue
        for item in found:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            if i:
                item["extra"] = (item["extra"] + " | via broader search").strip()
            items.append(item)
        if found:
            last_err = None
        elif last_err is None:
            last_err = f"SMK: 0 public-domain image hits for '{plan}'"
        if len(items) >= limit * 2:
            break

    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    items.sort(key=lambda item: _date_score(item["date_str"], rng))
    return items[:limit], last_err
