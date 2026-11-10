"""Library of Congress adapter - no key, fo=json. Tries /photos/ then /search/.
Uses native dates=lo/hi filter from the brief when a time period is set.
Query chain: full query+dates -> period-synonym variant+dates -> full query
unfiltered. One retry per call (LOC rate-limits bots intermittently)."""
import re
import time

from validator import brief_range, clean_query, wants_text

from .http import get

ENDPOINTS = ["https://www.loc.gov/photos/", "https://www.loc.gov/search/"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept": "application/json", "Referer": "https://www.loc.gov/photos/"}

def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""

def _width(url):
    m = re.search(r"[#&?]w=(\d+)", url or "")
    return int(m.group(1)) if m else 0

def _pick_urls(urls):
    """(thumb, full): skip placeholder SVGs; thumb = first real file (150px);
    full = widest 'r.jpg' reference (640px) so Photoshop drag-in is usable."""
    real = [u for u in urls if isinstance(u, str) and u and not u.lower().endswith(".svg")
            and "group-of-images.svg" not in u and "original-format" not in u]
    if not real:
        return None, None
    thumb = real[0]
    full = max(real, key=_width) if any(_width(u) for u in real) else real[-1]
    return thumb, full

def _parse(data, limit, keep_text=False, variant=None):
    items = []
    for it in (data.get("results", []) or []):
        if len(items) >= limit:
            break
        info = it.get("item") or {}
        fmt = "/".join(info.get("format") or []).lower()
        # verified 2026-10-14: photos 'still image'; books 'text';
        # newspapers 'newspapers' (e.g. "The Manning times" school papers)
        is_text = ("still image" not in fmt
                   and any(t in fmt for t in ("text", "book", "newspaper",
                                              "periodical", "magazine", "manuscript")))
        if is_text and not keep_text:
            continue  # books/newspapers/covers: validator would hide them; don't burn a slot
        raw = it.get("image_url") or info.get("image_url") or []
        if isinstance(raw, str):
            raw = [raw]
        thumb, full = _pick_urls(raw)
        if not thumb:
            continue  # no downloadable image (placeholder-only record)
        if any(t in fmt for t in ("text", "book", "newspaper", "periodical",
                                   "magazine", "manuscript")):
            medium = "Book/Text"
        else:
            medium = "Photograph"  # /photos/ endpoint default
        phys = " / ".join(info.get("medium") or [])
        repo = str(info.get("repository", ""))
        extra = repo + (" | " + phys if phys else "")
        if variant:
            extra = (extra + f" | via variant '{variant}'").strip()
        creator = it.get("contributor") or ""
        if isinstance(creator, list):
            creator = ", ".join(str(c) for c in creator if c)
        items.append({
            "id": "loc-" + str(it.get("id", "")),
            "title": it.get("title") or "(untitled)",
            "date_str": str(it.get("date") or ""),
            "creator": str(creator)[:80],
            "source": "LOC/" + str(_first(it.get("partof")) or "Library of Congress"),
            "image_url": full,
            "thumb_url": thumb,
            "page_url": it.get("url") or it.get("id") or "",
            "medium": medium,
            "extra": extra,
        })
    return items

def _get(api, params):
    last = None
    for _ in range(2):
        try:
            r = get(api, params=params, headers=UA, timeout=25)
            r.raise_for_status()
            return r.json(), None
        except Exception as e:
            last = e
            time.sleep(2)
    return None, last

def search(query, limit=6, brief=None):
    q = clean_query(query) or query
    rng = brief_range((brief or {}).get("time_period", "")) if brief else None
    # (query, use_dates): full+dates -> period synonym+dates -> full plain ->
    # shortened plain. Empty hits fall through fast; exceptions retry in _get.
    plan = [(q, bool(rng))]
    # period vocabulary: 19th-c. bars were "saloons" in US cataloging (verified:
    # 'saloon interior' returns 1888-1890 bar interiors where 'bar ...' does not)
    if rng and rng[0] < 1920 and any(w in q.lower() for w in ("bar", "pub")):
        plan.append(("saloon interior", True))
    short = " ".join(q.split(" ")[:3])
    if short and short != q:
        plan.append((short, False))
    plan.append((q, False))
    last_err = None
    keep_text = wants_text(brief or {})
    seen, out = set(), []
    for vq, dated in plan:
        # over-fetch: text/placeholder records are dropped in _parse, so ask
        # for extra to still fill the card grid with real photographs
        params = {"q": vq, "fo": "json", "c": max(6, min(limit * 3, 60))}
        if rng and dated:
            params["dates"] = f"{rng[0]}/{rng[1]}"
        for api in ENDPOINTS:
            data, err = _get(api, params)
            if err is not None:
                last_err = f"LOC: {err} (Cloudflare may 403 bots; retry on home network)"
                continue
            added = 0
            for it in _parse(data, limit * 3, keep_text, variant=(vq if vq != q else None)):
                if it["id"] in seen:
                    continue
                seen.add(it["id"])
                out.append(it)
                added += 1
                if len(out) >= limit:
                    break
            if not added:
                last_err = f"LOC: 0 usable photos for '{vq}' (try broader terms)"
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    if out:
        return out[:limit], None
    return [], last_err or "LOC: no results"
