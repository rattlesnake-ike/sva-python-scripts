"""Rule-based brief validator (no AI key needed, hand-checkable).

Verdicts:
  FITS      ✓ Fits        date in range, no exclusion hit
  POST      △ Post-brief  dated after brief range (e.g. 1930 for a 1920s brief)
  PRE       △ Pre-brief   dated before brief range
  MISMATCH  ✕ Mismatch    far outside range (>35y) or exclusion hit
  UNKNOWN   ? Unknown     no parseable date or fetch failed
"""
import re
from functools import lru_cache

CENTURIES = {"colonial": (1607, 1783)}

STOPWORDS = {"in", "of", "the", "a", "an", "and", "or", "for", "with", "from",
             "to", "at", "on", "by", "my", "i", "want", "draw", "painting",
             "image", "images", "photo", "please", "with", "without"}

@lru_cache(maxsize=512)
def keywords(text, cap=6):
    """Keyword extraction for search: lowercase, drop stopwords + date tokens +
    placeholder locations ('anywhere'), de-dupe, keep prompt order, cap length
    (long AND-queries zero out archives)."""
    s = re.sub(r"\b(1[0-9]\d{2}s?|20[0-2]\ds?)\b", " ", text.lower())
    s = re.sub(r"\b(1[0-9]|20)(st|nd|rd|th)\s+century\b", " ", s)
    out, seen = [], set()
    for w in re.findall(r"[a-z']{3,}", s):
        if w not in STOPWORDS and w not in ANYWHERE and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:cap]

@lru_cache(maxsize=4096)
def parse_years(date_str):
    """Return list of years found in a string, expanding '1920s' -> 1920..1929 range marker."""
    if not date_str:
        return []
    s = date_str.lower().replace("ca.", "").replace("c.", "").strip()
    years = []
    for m in re.finditer(r"(1[0-9]\d{2}|20[0-2]\d)s?", s):
        y = int(m.group(0)[:4])
        years.append(y)
        if m.group(0).endswith("s"):
            years.extend(range(y, y + 10))
    # century like '19th century' -> 1801..1900
    for m in re.finditer(r"(1[0-9]|20)th century", s):
        c = int(m.group(1))
        years.extend([ (c - 1) * 100 + 1, c * 100 ])
    return sorted(set(years))

@lru_cache(maxsize=4096)
def clean_query(text):
    """Strip date tokens (1890s, 1920s, 1875, '19th century') from a text query —
    they poison full-text search; dates go through each API's native filter."""
    s = re.sub(r"\b(1[0-9]\d{2}s?|20[0-2]\ds?)\b", " ", text)
    s = re.sub(r"\b(1[0-9]|20)(st|nd|rd|th)\s+century\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # de-dupe words, keep order
    seen, out = set(), []
    for w in s.split(" "):
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return " ".join(out)

@lru_cache(maxsize=256)
def brief_range(time_period):
    """Map '1920s' / '1890s' / '1750-1780' / 'colonial' -> (lo, hi). Default None.
    Pure and called once per candidate, so the result is memoized."""
    if not time_period:
        return None
    s = time_period.strip().lower()
    m = re.match(r"(1[0-9]\d{2})s$", s)
    if m:
        y = int(m.group(1))
        return (y, y + 9)
    m = re.match(r"(1[0-9]\d{2})\s*[-–]\s*(1[0-9]\d{2}|20[0-2]\d)", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.match(r"(\d{1,2})(st|nd|rd|th)\s*century", s)
    if m:
        c = int(m.group(1))
        return ((c - 1) * 100 + 1, c * 100)
    m = re.match(r"(1[0-9]\d{2}|20[0-2]\d)", s)
    if m:
        y = int(m.group(1))
        return (y, y + 9)
    for k, v in CENTURIES.items():
        if k in s:
            return v
    return None

BOOK_WORDS = {"book", "books", "cover", "covers", "novel", "novels", "magazine",
              "newspaper", "periodical", "pamphlet", "text", "catalogue"}
TEXT_FORMATS = ("book", "text", "periodical", "newspaper", "magazine", "manuscript")

# placeholder "locations" that must never become search keywords
ANYWHERE = {"anywhere", "any", "all", "n/a", "na", "none", "-", "any place",
            "anyplace", "everywhere", "worldwide", "global"}

def wants_text(brief):
    hay = (brief.get("title", "") + " " + " ".join(brief.get("styles", [])) + " "
           + brief.get("location", "")).lower()
    return any(w in hay for w in BOOK_WORDS)

def photo_gate(thumb_path, item, brief):
    """Color-era gate for dateless photo-like items. Returns 'modern' | 'ok' | 'skip'.

    Only judges when the brief ends before 1935 (pre-color era for practical
    photography) AND the item carries no parseable date AND the medium is not
    a painting/sculpture. Thresholds tuned on real hits 2026-10-14: modern
    Flickr portraits score sat~0.8-0.9/spread 2-5; B&W glass negatives ~0.0/0;
    sepia stays under sat 0.75 with <3 hue bins, so it passes.
    """
    rng = brief_range(brief.get("time_period", ""))
    if not rng or rng[1] >= 1935:
        return "skip"
    if parse_years(item.get("date_str") or ""):
        return "skip"  # dated items are judged by date, not pixels
    med = (item.get("medium") or "").lower()
    if any(k in med for k in ("paint", "oil", "canvas", "watercolor", "sculpture")):
        return "skip"
    try:
        from PIL import Image
        with Image.open(thumb_path) as im:
            hsv = im.convert("RGB").resize((120, 120)).convert("HSV")
            raw = hsv.tobytes()
        n = len(raw) // 3
        if n == 0:
            return "skip"
        bins = [0] * 12
        sat = 0
        for i in range(0, len(raw), 3):
            s, v = raw[i + 1], raw[i + 2]
            if s > 40 and v > 40:
                sat += 1
                bins[raw[i] * 12 // 256] += 1
        frac = sat / n
        spread = sum(1 for c in bins if c > n * 0.01)
        if (spread >= 3 and frac > 0.4) or frac > 0.75:
            return "modern"
        return "ok"
    except Exception:
        return "skip"

# prompt-word synonyms for the topicality check (normalized singulars)
SYNONYMS = {
    "portrait": ("portrayal", "bust", "statue", "likeness", "depiction", "effigy",
                 "head", "face", "visage", "medal", "medallion", "plaque", "cameo",
                 "miniature", "silhouette"),
    "man": ("men", "gentleman", "gentlemen", "male"),
    "woman": ("women", "lady", "ladies", "female", "madam", "madame"),
    "child": ("children", "boy", "girl", "baby", "infant"),
    "bar": ("saloon", "tavern", "pub", "alehouse", "taproom", "inn", "cantina",
            "speakeasy", "beer", "cocktail", "publichouse", "cabaret", "nightclub",
            "dancehall"),
    "pub": ("bar", "saloon", "tavern", "alehouse", "taproom", "inn", "publichouse"),
    "cafe": ("café", "coffeehouse", "bistro", "brasserie", "tearoom"),
    "church": ("cathedral", "chapel", "abbey", "basilica", "parish"),
    "street": ("avenue", "boulevard", "road", "lane", "square", "plaza"),
    "interior": ("inside", "room"),
    "paris": ("parisian",),
    "ireland": ("irish", "dublin", "belfast", "cork", "galway"),
    "london": ("londoner",),
}

def _norm(w):
    if w in ("paris", "texas"):
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith(("ss", "us")) and len(w) > 3:
        return w[:-1]
    return w

_IRREG = {"women": "woman", "men": "man", "children": "child",
          "teeth": "tooth", "feet": "foot", "mice": "mouse"}

def _canon(w):
    return _IRREG.get(w, _norm(w))

@lru_cache(maxsize=64)
def _topical_probe(title, styles, location):
    """Prompt-side topical work, memoized: the keywords and synonyms are the
    same for every candidate of one brief (hundreds per search)."""
    keys = keywords(title + " " + " ".join(styles) + " " + location, cap=8)
    if not keys:
        return None
    # a bare place word is not a topic: "St Fin Barre's Cathedral" must not pass
    # a bar brief on "Ireland" alone (unless place is the whole prompt)
    place_toks = {_canon(w) for w in re.findall(r"[a-z']{3,}", location.lower())}
    place_toks.update(_canon(s) for k in list(place_toks) for s in SYNONYMS.get(k, ()))
    content_keys = [k for k in keys if _canon(k) not in place_toks]
    probe = content_keys or keys
    expanded = set(probe)
    for k in probe:
        expanded.update(SYNONYMS.get(k, ()))
        expanded.update(SYNONYMS.get(_norm(k), ()))
    return frozenset(expanded)

def extract_phrases(text):
    """Quoted substrings in `text` (e.g. "ice cream") that must appear as a
    contiguous substring in a result's title/creator/medium."""
    return [m.group(1).strip() for m in re.finditer(r'"([^"]+)"', text or "")
            if m.group(1).strip()]


def topical(item, brief):
    """True if a prompt word (or synonym) appears whole-word in the record's
    title/artist/medium. Quoted phrases must appear as contiguous substrings.
    Guards 'only bring back what was requested'."""
    title = brief.get("title", "") or ""
    phrases = extract_phrases(title)
    hay_text = ((item.get("title") or "") + " " + (item.get("creator") or "") + " "
                + (item.get("medium") or "")).lower()
    # exact phrase match: every quoted phrase must appear as a whole
    # phrase (word-bounded, not embedded in a longer compound like
    # "ice cream truck"). Checked against the title first so a trailing
    # creator/medium name doesn't break the boundary; falls back to the full
    # text for records where the phrase lives in creator/medium.
    for ph in phrases:
        pat = re.compile(r'\b' + re.escape(ph) + r'(?![ \t]*\w)', re.IGNORECASE)
        title_l = (item.get("title") or "").lower()
        if pat.search(title_l):
            continue
        if not pat.search(hay_text):
            return False
    expanded = _topical_probe(title, tuple(brief.get("styles", [])),
                               brief.get("location", ""))
    if expanded is None:
        return True
    hay_words = {_canon(w) for w in re.findall(r"[a-z']{3,}", hay_text)}
    return any(_canon(k) in hay_words for k in expanded)


def validate(item, brief):
    """brief: dict(title,time_period,location,styles,media,exclude). Returns dict(verdict,label,reason)."""
    date_field = item.get("date_str") or ""
    backfill = (item.get("title") or "") + " " + (item.get("extra") or "")
    years = parse_years(date_field)
    used_backfill = False
    if not years:
        # structured date missing: fall back to years mentioned in title/extra
        years = parse_years(backfill)
        used_backfill = True
    rng = brief_range(brief.get("time_period", ""))
    exc = [e.lower() for e in brief.get("exclude", []) if e.strip()]
    hay = (item.get("title", "") + " " + item.get("extra", "") + " " + item.get("medium", "")).lower()
    loc = brief.get("location", "").lower()

    # exclusion hits (plural/synonym-aware: "women" catches "woman"/"ladies",
    # "children" catches "boy"/"girl", "Portraits" catches "portrait")
    hay_words = {_canon(w) for w in re.findall(r"[a-z']{3,}", hay)}
    for e in exc:
        if e in ("b&w", "b/w", "black and white") and ("black-and-white" in hay or "black and white" in hay):
            return {"verdict": "MISMATCH", "label": "✕ Mismatch", "reason": f"excluded: {e}"}
        elif e and e not in ("b&w", "b/w", "black and white"):
            if e in hay:
                return {"verdict": "MISMATCH", "label": "✕ Mismatch", "reason": f"excluded: {e}"}
            ew = [_canon(w) for w in re.findall(r"[a-z']{3,}", e)]
            expset = set(ew)
            for w in ew:
                expset.update(_canon(s) for s in SYNONYMS.get(w, ()))
            if expset & hay_words:
                return {"verdict": "MISMATCH", "label": "✕ Mismatch", "reason": f"excluded: {e}"}

    # book/text formats (covers, title pages, bound volumes): hidden unless asked for
    medium = (item.get("medium") or "").lower()
    if any(t in medium for t in TEXT_FORMATS) and not wants_text(brief):
        return {"verdict": "MISMATCH", "label": "✕ Mismatch",
                "reason": "book/text format (cover/pages) — not requested in brief"}

    # exact phrase match: every quoted phrase must appear as a whole
    # phrase (not embedded in a longer compound like "ice cream truck")
    phrases = extract_phrases(brief.get("title", "") or "")
    title_l = (item.get("title") or "").lower()
    hay = (item.get("title", "") + " " + (item.get("creator") or "") + " "
           + (item.get("medium") or "")).lower()
    for ph in phrases:
        pat = re.compile(r'\b' + re.escape(ph) + r'(?![ \t]*\w)', re.IGNORECASE)
        if pat.search(title_l):
            continue
        if not pat.search(hay):
            return {"verdict": "MISMATCH", "label": "✕ Mismatch",
                    "reason": f'phrase not found: "{ph}"'}
    # topicality: nothing the prompt didn't ask for
    if not topical(item, brief):
        return {"verdict": "MISMATCH", "label": "✕ Mismatch",
                "reason": "off-topic: no prompt word in title/artist/medium"}

    if not rng:
        return {"verdict": "UNKNOWN", "label": "? Unknown", "reason": "no brief range set"}
    if not years:
        # location hint can still rescue a weak fit
        if loc and any(t in hay for t in loc.replace(",", " ").split() if len(t) > 2):
            return {"verdict": "UNKNOWN", "label": "? Unknown", "reason": "no date; place matches, verify date at source"}
        return {"verdict": "UNKNOWN", "label": "? Unknown", "reason": "no parseable date; verify at source"}
    if len(years) > 12:
        # exhaustive year lists (e.g. 40 dates on a church record) — no focused date
        return {"verdict": "UNKNOWN", "label": "? Unknown",
                "reason": f"{len(years)} dates listed, no focused date; verify at source"}
    if len(years) > 1:
        run, best = 1, 1
        for a, b in zip(years, years[1:]):
            run = run + 1 if b == a + 1 else 1
            best = max(best, run)
        if best < len(years):
            # scattered years (title noise like "1792 1837 1914") — no focused date
            return {"verdict": "UNKNOWN", "label": "? Unknown",
                    "reason": f"{len(years)} scattered dates, no focused date; verify at source"}
    src_note = " (date from title/text — confirm at source)" if (used_backfill and years) else ""

    place = ""
    if loc:
        toks = [t for t in loc.replace(",", " ").split() if len(t) > 2]
        place = "; place match" if any(t in hay for t in toks) else "; place unverified"

    lo, hi = rng
    in_range = any(lo <= y <= hi for y in years)
    if in_range:
        return {"verdict": "FITS", "label": "✓ Fits", "reason": f"{min(years)} in {lo}-{hi}{place}{src_note}"}
    nearest = min(years, key=lambda y: min(abs(y - lo), abs(y - hi)))
    gap = 0 if lo <= nearest <= hi else (nearest - hi if nearest > hi else lo - nearest)
    if gap <= 12:
        tag = "Post-brief" if nearest > hi else "Pre-brief"
        return {"verdict": "POST" if nearest > hi else "PRE", "label": f"△ {tag}",
                "reason": f"{nearest} vs brief {lo}-{hi}{place}{src_note}"}
    return {"verdict": "MISMATCH", "label": "✕ Mismatch",
            "reason": f"{nearest} vs brief {lo}-{hi} ({gap}y off){place}{src_note}"}
