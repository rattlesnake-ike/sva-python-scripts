"""Europeana adapter (https://api.europeana.eu — Search API v2).

Millions of records from 1000s of European heritage institutions; strong for
Paris / Ireland / 1890s-type briefs, with open-reuse filtering so every hit is
safe to draw from. Uses native YEAR:[lo TO hi] range filter from the brief
(verified working 2026-10-14), falling back to unfiltered on zero hits.

Endpoint: https://api.europeana.eu/record/v2/search.json
Key: env EUROPEANA_API_KEY or local .europeana_key file.
"""
import os

from validator import brief_range, clean_query

from .http import get

API = "https://api.europeana.eu/record/v2/search.json"
UA = {"User-Agent": "AI-Reference-Retriever/1.0 (student midterm)"}
KEY_URL = "https://pro.europeana.eu/pages/get-api"

def _key():
    k = (os.environ.get("EUROPEANA_API_KEY") or "").strip()
    if k:
        return k
    try:  # local key file (written once, no need to set env every run)
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", ".europeana_key"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""

def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""

def _parse(data, limit):
    items = []
    for it in data.get("items", [])[:limit]:
        rights = _first(it.get("rights"))
        dc = it.get("dcCreator")
        creator = ", ".join(dc) if isinstance(dc, list) else str(dc or "")
        yr = it.get("year")
        # keep the whole year list (capped): a single focused year -> Fits;
        # an exhaustive list (40 dates) -> validator's multi-year guard -> '?'
        date_str = ", ".join(str(y) for y in yr[:8]) if isinstance(yr, list) else str(yr or "")
        items.append({
            "id": "eu-" + str(it.get("id", "")).strip("/"),
            "title": _first(it.get("title")) or "(untitled)",
            "date_str": date_str,
            "creator": creator,
            "source": "Europeana/" + str(_first(it.get("dataProvider")) or _first(it.get("provider")) or "provider"),
            "image_url": _first(it.get("edmIsShownBy")) or _first(it.get("edmPreview")) or "",
            "thumb_url": _first(it.get("edmPreview")) or "",
            "page_url": it.get("guid") or _first(it.get("edmIsShownAt")) or "",
            "medium": str(it.get("type") or ""),
            "extra": rights,
        })
    return items

def _candidates(q, brief):
    """Site-faithful order: the user's own keywords (+ period facet) first;
    shortened/synonym fallbacks only after, each labeled so a hit is always
    traceable to the query that produced it (like the site's own history)."""
    loc_toks = set()
    if brief:
        for w in str(brief.get("location", "")).replace(",", " ").split():
            if len(w) > 2:
                loc_toks.add(w.lower())
    words = q.split(" ")
    nolo = " ".join(w for w in words if w.lower() not in loc_toks).strip()
    core = " ".join(sorted(words, key=len, reverse=True)[:2])
    cands = [q]
    if brief:
        rng2 = brief_range(brief.get("time_period", "") or "")
        if rng2 and rng2[0] < 1920 and any(w in q.lower() for w in ("bar", "pub")):
            if "bar room interior" not in cands:
                cands.append("bar room interior")
    for c in (nolo, core):
        if c and c != q and c not in cands:
            cands.append(c)
    return cands

def search(query, limit=6, brief=None):
    key = _key()
    if not key:
        return [], (f"Europeana: no API key. Free key (1 min signup): {KEY_URL} "
                     "then set EUROPEANA_API_KEY and search again.")
    q = clean_query(query) or query
    year_qf = None
    if brief:
        rng = brief_range(brief.get("time_period", ""))
        if rng:
            year_qf = f"YEAR:[{rng[0]} TO {rng[1]}]"
    # Faithful first: user's keywords + period facet (the site's date filter),
    # then the same keywords unfiltered (the site's default view), then labeled
    # fallbacks. europeana.eu shows undated/loose hits too — the validator, not
    # the query, is what hides true mismatches.
    cands = _candidates(q, brief)
    qf_sets = []
    if year_qf:
        qf_sets.append(("YEAR", cands[0]))
    qf_sets.append(("plain", cands[0]))
    if year_qf:
        qf_sets += [("YEAR", c) for c in cands[1:]]
    last_err = None
    seen, out = set(), []
    for tag, qc in qf_sets:
        qf = ["TYPE:IMAGE"] + ([year_qf] if tag == "YEAR" else [])
        try:
            r = get(API, params={
                "wskey": key,
                "query": qc,
                "qf": qf,
                "reusability": "open",
                "rows": max(10, min(limit * 3, 100)),
                "profile": "rich",
                "media": "true",
                "thumbnail": "true",
            }, headers=UA, timeout=25)
            if r.status_code in (401, 403):
                return list(out), "Europeana: key rejected (401/403) — check EUROPEANA_API_KEY."
            r.raise_for_status()
            data = r.json()
            if not data.get("success"):
                last_err = f"Europeana: API error {str(data.get('error'))[:120]}"
                continue
            added = 0
            for it in _parse(data, limit * 3):
                if it["id"] in seen:
                    continue
                seen.add(it["id"])
                if qc != q:
                    it["extra"] = (it["extra"] + f" | via variant '{qc}'").strip(" |")
                out.append(it)
                added += 1
                if len(out) >= limit:
                    break
            if not added:
                last_err = f"Europeana: 0 new hits for '{qc}' ({tag})"
            if len(out) >= limit:
                break
        except Exception as e:
            last_err = f"Europeana: {str(e)[:150]}"
            continue
    if out:
        return out[:limit], None
    return [], last_err or "Europeana: no results"
