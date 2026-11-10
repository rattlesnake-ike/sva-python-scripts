"""Internet Archive adapter (https://archive.org — keyless advanced search).

The Internet Archive exposes a Lucene advanced-search endpoint and an image
service. Only items whose `licenseurl` explicitly contains "publicdomain"
(Public Domain Mark or CC0) are returned; copyrighted or unspecified-license
items are skipped. A date is required because this tool only trusts dated
sources.

The archive's image service returns a stable JPEG preview for an item; that
preview is used for both the grid thumbnail and the drag-in file. Full
original files vary by item and are not fetched here.
"""
import re

from validator import brief_range, clean_query, parse_years

from .http import get

SEARCH = "https://archive.org/advancedsearch.php"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _as_list(value):
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def _date_str(record):
    return _clean(record.get("date"))


def _creator(record):
    return ", ".join(_clean(x) for x in _as_list(record.get("creator")) if _clean(x))[:80]


def _title(record):
    return _clean(record.get("title")) or "(untitled)"


def _medium(record):
    subjects = [ _clean(x) for x in _as_list(record.get("subject")) if _clean(x) ]
    return " / ".join(dict.fromkeys(subjects))[:80] or "Image"


def _is_public_domain(record):
    license_url = _clean(record.get("licenseurl")).lower()
    return "publicdomain" in license_url


def _to_item(record):
    identifier = _clean(record.get("identifier"))
    preview = f"https://archive.org/services/img/{identifier}"
    return {
        "id": "ia-" + identifier,
        "title": _title(record),
        "date_str": _date_str(record),
        "creator": _creator(record),
        "source": "Internet Archive",
        "image_url": preview,
        "thumb_url": preview,
        "large_url": preview,
        "page_url": f"https://archive.org/details/{identifier}",
        "medium": _medium(record),
        "extra": "Public domain (Internet Archive) | " + _clean(record.get("licenseurl")),
    }


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


def _fetch(query, limit, brief=None):
    q = f'mediatype:image AND licenseurl:*publicdomain* AND (title:"{query}" OR description:"{query}")'
    r = get(SEARCH, params={
        "q": q,
        "fl[]": ["identifier", "title", "creator", "date", "licenseurl", "subject"],
        "rows": 100,
        "output": "json",
    }, headers=UA, timeout=30)
    r.raise_for_status()
    data = r.json()
    docs = (data.get("response") or {}).get("docs") or []
    items = []
    for record in docs:
        if not _is_public_domain(record):
            continue
        if not _date_str(record):
            continue
        items.append(_to_item(record))
        if len(items) >= max(30, limit * 6):
            break
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    items.sort(key=lambda item: _date_score(item["date_str"], rng))
    return items[:limit]


def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    items, seen, last_err = [], set(), None
    for i, plan in enumerate([q] + ([q.split()[0]] if len(q.split()) > 1 else [])):
        try:
            found = _fetch(plan, limit, brief)
        except Exception as e:
            last_err = f"Internet Archive: {str(e)[:130]}"
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
            last_err = f"Internet Archive: 0 public-domain image hits for '{plan}'"
        if len(items) >= limit * 2:
            break
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    items.sort(key=lambda item: _date_score(item["date_str"], rng))
    return items[:limit], last_err