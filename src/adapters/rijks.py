"""Rijksmuseum adapter (https://data.rijksmuseum.nl — keyless Linked Art).

The Search API returns object IDs; each ID is resolved with the Persistent
Identifier Resolver. Only objects whose *image* DigitalObject carries the
Rijksmuseum's "Public Domain" statement (or a CC Public Domain Mark/CC0 URL)
are returned. The collection metadata itself is CC0, but that does NOT mean
every image is PD, so the object-level license is deliberately ignored here.

Search supports `imageAvailable=true` and a wildcard `creationDate` (for
example `189?` for the 1890s). Images are IIIF: 843px preview + 1600px
drag-in tier. Undated records and records without a PD image are skipped.
"""
import html
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import quote

from validator import brief_range, clean_query, parse_years

from .http import get

SEARCH = "https://data.rijksmuseum.nl/search/collection"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)",
      "Accept": "application/ld+json"}
PD_MARKERS = ("publicdomain/mark", "publicdomain/zero")
ROLES = {"printmaker", "painter", "artist", "maker", "designer", "engraver",
         "photographer", "draftsman", "etcher", "lithographer", "sculptor"}


def _clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _as_list(value):
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def _names(values):
    """Collect human-readable names from Linked Art name/notation fields."""
    out = []
    for value in _as_list(values):
        if not isinstance(value, dict):
            continue
        notation = value.get("notation")
        for note in _as_list(notation):
            if isinstance(note, dict) and note.get("@value"):
                out.append(_clean(note["@value"]))
        if value.get("type") == "Name" and value.get("content"):
            out.append(_clean(value["content"]))
        if value.get("_label"):
            out.append(_clean(value["_label"]))
    return [x for x in dict.fromkeys(out) if x]


def _english_notations(values):
    out = []
    for value in _as_list(values):
        if not isinstance(value, dict):
            continue
        for note in _as_list(value.get("notation")):
            if not isinstance(note, dict):
                continue
            if note.get("@language") == "en" and note.get("@value"):
                out.append(_clean(note["@value"]))
        if value.get("_label"):
            out.append(_clean(value["_label"]))
    return [x for x in dict.fromkeys(out) if x]


def _title(obj):
    names = _names(obj.get("identified_by"))
    return max(names, key=len)[:140] if names else "(untitled)"


def _creator(obj):
    role_names, actor_names = [], []
    production = obj.get("produced_by") or {}
    parts = _as_list(production.get("part") if isinstance(production, dict) else production)
    for part in parts:
        if not isinstance(part, dict):
            continue
        for actor in _as_list(part.get("carried_out_by")):
            actor_names.extend(_names(actor))
        for note in _as_list(part.get("referred_to_by")):
            if not isinstance(note, dict):
                continue
            content = _clean(note.get("content"))
            if ":" not in content:
                continue
            role, value = content.split(":", 1)
            if role.strip().lower() not in ROLES:
                continue
            value = re.sub(
                r"\s*\((?:mentioned on object|vermeld op object|[0-9]{4}-[0-9]{4})\)\s*$",
                "", value, flags=re.I).strip()
            if value:
                role_names.append(value)
    # Prefer explicit "printmaker: ..."/"painter: ..." strings: they identify
    # the artist, while carried_out_by can also name the printer or publisher.
    out = role_names or actor_names
    out = [re.sub(r"\s*\((?:mentioned on object|vermeld op object)\)", "", x,
                  flags=re.I).strip() for x in out]
    return ", ".join(dict.fromkeys(x for x in out if x))[:80]


def _dates(obj):
    out = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("type") == "TimeSpan":
                for name in _as_list(value.get("identified_by")):
                    if isinstance(name, dict):
                        content = _clean(name.get("content"))
                        if content and re.search(r"\d{3,4}", content):
                            out.append(content)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(obj.get("produced_by"))
    return ", ".join(dict.fromkeys(out))[:80]


def _medium(obj):
    out = _english_notations(obj.get("classified_as"))
    out += _english_notations(obj.get("made_of"))
    return " / ".join(dict.fromkeys(out))[:80]


def _image(obj):
    """Return the IIIF image URL only when the image itself is PD."""
    for subject in _as_list(obj.get("subject_of")):
        if not isinstance(subject, dict):
            continue
        for digital in _as_list(subject.get("digitally_carried_by")):
            if not isinstance(digital, dict):
                continue
            image = ""
            for point in _as_list(digital.get("access_point")):
                if isinstance(point, dict):
                    url = _clean(point.get("id"))
                    if "iiif.micr.io" in url:
                        image = url
                        break
            if not image:
                continue
            statements = _as_list(digital.get("referred_to_by"))
            labels = " ".join(
                _clean(s.get("_label")) for s in statements if isinstance(s, dict)
            ).lower()
            content = " ".join(
                _clean(s.get("content")) for s in statements if isinstance(s, dict)
            ).lower()
            if "public domain" in labels or any(marker in content for marker in PD_MARKERS):
                return image
    return ""


def _page(obj):
    for subject in _as_list(obj.get("subject_of")):
        if not isinstance(subject, dict):
            continue
        for digital in _as_list(subject.get("digitally_carried_by")):
            if not isinstance(digital, dict):
                continue
            if str(digital.get("format") or "").lower() != "text/html":
                continue
            for point in _as_list(digital.get("access_point")):
                if isinstance(point, dict) and point.get("id"):
                    return _clean(point["id"])
    number = _object_number(obj)
    if number:
        return f"https://www.rijksmuseum.nl/en/collection/{quote(number)}"
    return "https://www.rijksmuseum.nl/en/collection"


def _object_number(obj):
    candidates = []
    for item in _as_list(obj.get("identified_by")):
        if not isinstance(item, dict) or item.get("type") != "Identifier":
            continue
        content = _clean(item.get("content"))
        if content and "http" not in content.lower() and len(content) <= 40:
            candidates.append(content)
    # Prefer a real object number (letters/hyphens) over internal numeric ids.
    for content in candidates:
        if re.search(r"[A-Za-z]", content) and len(content) >= 3:
            return content
    return ""


def _tier(url, size):
    return re.sub(r"/full/[^/]+/", f"/full/{size}/", url) if "/full/" in url else url


def _to_item(obj):
    image = _image(obj)
    date = _dates(obj)
    if not image or not date:
        return None
    number = _object_number(obj)
    if not number:
        match = re.search(r"iiif\.micr\.io/([^/]+)/", image)
        number = match.group(1) if match else "unknown"
    large = _tier(image, "!1600,1600")
    return {
        "id": "rijks-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", number),
        "title": _title(obj),
        "date_str": date,
        "creator": _creator(obj),
        "source": "Rijksmuseum",
        "image_url": large,
        "thumb_url": _tier(image, "!843,843"),
        "large_url": large,
        "page_url": _page(obj),
        "medium": _medium(obj),
        "extra": "Public domain (Rijksmuseum) | CC0/PDM",
    }


def _date_wildcard(rng):
    """Use the API's native creationDate wildcard only when it is precise."""
    if not rng:
        return ""
    lo, hi = rng
    if lo // 10 == hi // 10:
        return f"{lo // 10}?"
    if lo // 100 == hi // 100:
        return f"{lo // 100}??"
    return ""


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


def _search(params):
    r = get(SEARCH, params=params, headers=UA, timeout=25)
    r.raise_for_status()
    data = r.json()
    return [item.get("id") for item in data.get("orderedItems") or []
            if isinstance(item, dict) and item.get("id")]


@lru_cache(maxsize=512)
def _resolve(object_id):
    try:
        r = get(object_id, headers=UA, timeout=25)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    wildcard = _date_wildcard(rng)
    words = q.split()

    core = words[0] if len(words) > 1 else ""
    plans = []
    # Date-filtered searches come first: a broad no-date search can otherwise
    # fill the scan budget with 17th-century paintings before the 1890s core
    # query is ever tried.
    for field in ("title", "description"):
        params = {field: q, "imageAvailable": "true"}
        if wildcard:
            params["creationDate"] = wildcard
        plans.append(params)
    if core:
        for field in ("title", "description"):
            params = {field: core, "imageAvailable": "true"}
            if wildcard:
                params["creationDate"] = wildcard
            plans.append(params)
    for field in ("title", "description"):
        plans.append({field: q, "imageAvailable": "true"})
    if core:
        for field in ("title", "description"):
            plans.append({field: core, "imageAvailable": "true"})

    # Preserve order but drop exact duplicates (the no-date plans are shared
    # when a brief has no usable wildcard).
    seen_plans, unique_plans = set(), []
    for params in plans:
        key = tuple(sorted(params.items()))
        if key not in seen_plans:
            seen_plans.add(key)
            unique_plans.append(params)

    max_scan = min(60, max(32, limit * 4))
    ids, seen_ids, last_err = [], set(), None
    for params in unique_plans:
        try:
            found = _search(params)
        except Exception as e:
            last_err = f"Rijksmuseum: {str(e)[:130]}"
            continue
        for object_id in found:
            if object_id not in seen_ids:
                seen_ids.add(object_id)
                ids.append(object_id)
        if len(ids) >= max_scan:
            break

    if not ids:
        return [], last_err or f"Rijksmuseum: 0 hits for '{q}'"

    with ThreadPoolExecutor(max_workers=8) as pool:
        objects = list(pool.map(_resolve, ids[:max_scan]))

    items = []
    for obj in objects:
        if not obj:
            continue
        item = _to_item(obj)
        if not item:
            continue
        items.append(item)
        if len(items) >= limit:
            break

    if not items:
        return [], f"Rijksmuseum: scanned {len(objects)} records, none were dated public-domain images"
    items.sort(key=lambda item: _date_score(item["date_str"], rng))
    return items[:limit], None
