"""OpenVerse adapter - live, no key. https://api.openverse.org/v1/images/

Restricted to public-domain-for-commercial-use works (license=pdm,cc0) and to
records whose title/creator/tags contain a prompt keyword — OpenVerse has no
artwork dates, so topical match is all we can verify here; the validator marks
these '?' (verify date at source before use).
"""
import html as _html
import re
import time

from validator import clean_query

from .http import get

API = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm; contact: local)"}

def _text(raw):
    return _html.unescape(re.sub(r"<[^>]+>", " ", raw or "")).strip(" :;,-")

def _params(q, limit):
    return {"q": q, "page_size": max(1, min(limit, 20)),
            "license": "pdm,cc0", "mature": "false"}

def _on_topic(it, tokens):
    hay = ((it.get("title") or "") + " " + (it.get("creator") or "") + " "
           + " ".join(t.get("name", "") for t in (it.get("tags") or []) if isinstance(t, dict))).lower()
    return any(t in hay for t in tokens)

def _fetch(q, limit, brief):
    last = None
    for _ in range(2):
        try:
            r = get(API, params=_params(q, limit), headers=UA, timeout=25)
            r.raise_for_status()
            return r.json().get("results", []) or [], None
        except Exception as e:
            last = e
            time.sleep(2)
    return None, last

def search(query, limit=6, brief=None):
    base = clean_query(query) or query
    tokens = [t for t in base.lower().split(" ") if len(t) > 2]
    tries = [base]
    short = " ".join(base.split(" ")[:2])
    if short and short != base:
        tries.append(short)
    last, raws = None, []
    for q in tries:
        raws, last = _fetch(q, limit, brief)
        if raws is None:
            continue  # error: retry path already exhausted in _fetch
        if raws:
            break
    if raws is None:
        return [], f"OpenVerse: {last} (retry on home network or broaden terms)"
    if not raws:
        return [], f"OpenVerse: 0 PD hits for '{base}' (try broader terms)"
    items = []
    for it in raws[:limit]:
        if tokens and not _on_topic(it, tokens):
            continue  # not what was requested
        lic = (it.get("license") or "").lower()
        if lic not in ("pdm", "cc0", "publicdomain"):
            continue
        items.append({
            "id": "ov-" + str(it.get("id", "")),
            "title": _text(it.get("title")) or "(untitled)",
            "date_str": "",
            "creator": _text(it.get("creator")) or "",
            "source": "OpenVerse/" + str(it.get("provider") or it.get("source") or "open"),
            "image_url": it.get("url") or it.get("thumbnail") or "",
            "thumb_url": it.get("thumbnail") or it.get("url") or "",
            "large_url": it.get("thumbnail") or it.get("url") or "",
            "page_url": it.get("foreign_landing_url") or it.get("detail_url") or "",
            "medium": "",
            "extra": ((it.get("license") or "") + " public domain").strip(),
        })
    if not items:
        return [], f"OpenVerse: PD records found but none matched '{base}' (off-topic filtered)"
    return items, None
