"""AI Reference Retriever - Production Processor (Midterm, Oct-20 milestone).
Standalone panel that mirrors the Photoshop-panel mockup. stdlib + requests + pillow + reportlab.
Run:  python app.py
"""
import os, json, copy, re, threading, queue, time, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, wait as _wait_all
from concurrent.futures import TimeoutError as _SearchTimeout
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from validator import validate, clean_query, keywords, photo_gate, parse_years

_IM = {}
_AD = {}

def _need_imaging():
    """Import PIL on first use (keeps cold startup to stdlib+tkinter)."""
    if "Image" not in _IM:
        from PIL import Image, ImageTk
        _IM["Image"], _IM["ImageTk"] = Image, ImageTk
    return _IM["Image"], _IM["ImageTk"]

def _adapters():
    """Import all source adapters on first search (pulls in requests)."""
    if "ADAPTERS" not in _AD:
        from adapters import ADAPTERS
        _AD["ADAPTERS"] = ADAPTERS
    return _AD["ADAPTERS"]
import store

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache")
BOARD = os.path.join(BASE, "board")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(BOARD, exist_ok=True)

VERSION = "2026-10-15o"

# ---------------------------------------------------------------- theme ----
# Photoshop's dark UI, so the tool sits in the same visual world as the
# Photoshop panel that launches it.
PS_BG = "#323232"          # panel background
PS_SURFACE = "#2b2b2b"     # cards, wells, scrollbar troughs
PS_BORDER = "#454545"      # hairlines
PS_FIELD = "#1e1e1e"       # input fields
PS_TEXT = "#e3e3e3"        # primary text
PS_TEXT_2 = "#a5a5a5"      # secondary text, section labels
PS_TEXT_3 = "#7d7d7d"      # tertiary text, disabled
PS_BTN = "#454545"
PS_BTN_HOVER = "#525252"
PS_BTN_ACTIVE = "#3a3a3a"
PS_BTN_BORDER = "#545454"
PS_ACCENT = "#1473e6"      # Adobe blue
PS_ACCENT_HOVER = "#0d66d0"
PS_FONT = ("Segoe UI", 10)
PS_FONT_SM = ("Segoe UI", 9)
PS_FONT_XS = ("Segoe UI", 8)

# validation verdict -> status colour, as Photoshop colour-codes status
PS_VERDICT = {
    "FITS": "#6cc26b",      # green
    "POST": "#e0a336",      # amber
    "PRE": "#e0a336",       # amber
    "MISMATCH": "#e5534b",  # red
    "UNKNOWN": "#a5a5a5",   # grey
}


def _style(self):
    """Style every ttk widget like a Photoshop panel (clam + dark palette)."""
    st = ttk.Style(self)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure(".",
                 background=PS_BG, foreground=PS_TEXT, fieldbackground=PS_FIELD,
                 bordercolor=PS_BORDER, darkcolor=PS_BG, lightcolor=PS_BG,
                 insertcolor=PS_TEXT, selectbackground=PS_ACCENT,
                 selectforeground="#ffffff", font=PS_FONT, borderwidth=0)
    st.configure("TFrame", background=PS_BG)
    st.configure("TLabel", background=PS_BG, foreground=PS_TEXT, font=PS_FONT)
    st.configure("Muted.TLabel", background=PS_BG, foreground=PS_TEXT_3,
                 font=PS_FONT_SM)
    st.configure("Section.TLabel", background=PS_BG, foreground=PS_TEXT_2,
                 font=("Segoe UI", 10, "bold"))
    st.configure("TLabelFrame", background=PS_BG, bordercolor=PS_BORDER,
                 relief="solid", borderwidth=1)
    st.configure("TLabelframe.Label", background=PS_BG, foreground=PS_TEXT_2,
                 font=("Segoe UI", 10, "bold"))
    st.configure("Card.TFrame", background=PS_SURFACE, bordercolor=PS_BORDER,
                 relief="solid", borderwidth=1)
    st.configure("TEntry", fieldbackground=PS_FIELD, foreground=PS_TEXT,
                 bordercolor=PS_BORDER, insertcolor=PS_TEXT,
                 lightcolor=PS_FIELD, darkcolor=PS_FIELD, borderwidth=1)
    st.map("TEntry", bordercolor=[("focus", PS_ACCENT)])
    st.configure("TCombobox", fieldbackground=PS_FIELD, foreground=PS_TEXT,
                 bordercolor=PS_BORDER, arrowcolor=PS_TEXT_2,
                 lightcolor=PS_FIELD, darkcolor=PS_FIELD, borderwidth=1)
    st.map("TCombobox",
           fieldbackground=[("readonly", PS_FIELD), ("hover", PS_FIELD)],
           foreground=[("readonly", PS_TEXT)],
           bordercolor=[("focus", PS_ACCENT), ("hover", PS_BORDER)])
    st.configure("Listbox", background=PS_FIELD, foreground=PS_TEXT,
                 selectbackground=PS_ACCENT, selectforeground="#ffffff",
                 bordercolor=PS_BORDER, highlightcolor=PS_BG,
                 highlightbackground=PS_FIELD, font=PS_FONT)
    st.configure("TCheckbutton", background=PS_BG, foreground=PS_TEXT,
                 indicatorcolor=PS_FIELD, indicatorbackground=PS_FIELD,
                 bordercolor=PS_BORDER, focuscolor=PS_BG, font=PS_FONT)
    st.map("TCheckbutton",
           indicatorcolor=[("selected", PS_ACCENT), ("active", PS_TEXT_2)],
           background=[("active", PS_BG)])
    st.configure("TButton", background=PS_BTN, foreground=PS_TEXT,
                 bordercolor=PS_BTN_BORDER, focuscolor=PS_BG,
                 darkcolor=PS_BTN, lightcolor=PS_BTN,
                 padding=(10, 5), relief="flat", borderwidth=1, font=PS_FONT)
    st.map("TButton",
           background=[("disabled", PS_BG), ("pressed", PS_BTN_ACTIVE),
                       ("active", PS_BTN_HOVER)],
           foreground=[("disabled", PS_TEXT_3)],
           bordercolor=[("disabled", PS_BORDER), ("active", PS_BTN_BORDER)])
    st.configure("Accent.TButton", background=PS_ACCENT, foreground="#ffffff",
                 bordercolor=PS_ACCENT, focuscolor=PS_ACCENT,
                 darkcolor=PS_ACCENT, lightcolor=PS_ACCENT,
                 padding=(14, 6), relief="flat", borderwidth=1,
                 font=("Segoe UI", 10, "bold"))
    st.map("Accent.TButton",
           background=[("disabled", PS_BORDER), ("pressed", PS_ACCENT_HOVER),
                       ("active", PS_ACCENT_HOVER)],
           foreground=[("disabled", PS_TEXT_3)],
           bordercolor=[("disabled", PS_BORDER), ("active", PS_ACCENT)])
    # the small buttons on a result card (ttk buttons take no font option,
    # so the size has to come from the style)
    st.configure("Card.TButton", background=PS_BTN, foreground=PS_TEXT,
                 bordercolor=PS_BTN_BORDER, focuscolor=PS_SURFACE,
                 darkcolor=PS_BTN, lightcolor=PS_BTN,
                 padding=(4, 2), relief="flat", borderwidth=1, font=PS_FONT_SM)
    st.map("Card.TButton",
           background=[("disabled", PS_SURFACE), ("pressed", PS_BTN_ACTIVE),
                       ("active", PS_BTN_HOVER)],
           foreground=[("disabled", PS_TEXT_3)],
           bordercolor=[("disabled", PS_BORDER), ("active", PS_BTN_BORDER)])
    st.configure("TProgressbar", background=PS_ACCENT, troughcolor=PS_SURFACE,
                 bordercolor=PS_SURFACE, lightcolor=PS_ACCENT,
                 darkcolor=PS_ACCENT, thickness=4)
    for orient in ("Vertical", "Horizontal"):
        st.configure(orient + ".TScrollbar", background=PS_BTN,
                     troughcolor=PS_SURFACE, bordercolor=PS_BG,
                     arrowcolor=PS_TEXT_2, darkcolor=PS_BTN,
                     lightcolor=PS_BTN, borderwidth=0, arrowsize=12)
        st.map(orient + ".TScrollbar",
               background=[("pressed", PS_BTN_ACTIVE), ("active", PS_BTN_HOVER)])
    # the draggable dividers between the panes: a plain hairline, not a bar
    st.configure("Sash", sashthickness=4, gripcount=0, background=PS_BORDER,
                 bordercolor=PS_BORDER, lightcolor=PS_BORDER, darkcolor=PS_BORDER)


def _dark_titlebar(win):
    """Paint the Windows caption bar in the panel colour (Windows 10/11)."""
    try:
        import ctypes
        dwm = ctypes.windll.dwmapi
        user32 = ctypes.windll.user32
        hwnd = user32.GetAncestor(win.winfo_id(), 2)   # GA_ROOT
        if not hwnd:
            return
        for attr, rgb in ((35, 0x323232), (36, 0xE3E3E3)):
            c = ctypes.c_int(rgb)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(c), ctypes.sizeof(c))
    except Exception:
        pass  # older Windows, or no DWM - the light caption bar is fine


_LOG_LOCK = threading.Lock()

def logline(msg):
    # search workers and UI callbacks both log; serialize so lines never interleave
    try:
        with _LOG_LOCK:
            with open(os.path.join(BOARD, "search_log.txt"), "a", encoding="utf-8") as f:
                f.write(datetime.datetime.now().strftime("%H:%M:%S") + " " + msg + "\n")
    except Exception:
        pass

_singleton_sock = None

def _ensure_single_instance(port=47911):
    """One retriever at a time: extra launches focus the open window and quit."""
    import socket
    import sys
    global _singleton_sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
    except OSError:
        _focus_existing()
        sys.exit(0)
    _singleton_sock = s  # held open for the app's lifetime
    return s

def _focus_existing():
    try:
        import ctypes
        from ctypes import wintypes
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _lp):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value.startswith("PRODUCTION PROCESSOR"):
                    found.append(hwnd)
            return True

        ctypes.windll.user32.EnumWindows(_cb, 0)
        for hwnd in found:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

_DL_LOCKS = {}
_DL_LOCKS_GUARD = threading.Lock()

def _dest_lock(dest):
    """One lock per destination file: a thumb, its prefetch and the lightbox can
    all want the same path at once; serializing them avoids duplicate downloads
    and lets a reader only ever see a fully written file."""
    key = os.path.abspath(dest)
    with _DL_LOCKS_GUARD:
        lock = _DL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _DL_LOCKS[key] = lock
        return lock

def _download(url, dest, retries=2, limit=15_000_000):
    """Fetch a URL to disk with retries (chunked, one writer per destination);
    raises on failure and never leaves a partial file behind."""
    lock = _dest_lock(dest)
    with lock:
        last = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as r, open(dest, "wb") as f:
                    remaining = limit
                    while remaining > 0:
                        chunk = r.read(min(65536, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                if os.path.getsize(dest) >= 500:
                    return dest
                last = Exception("tiny/empty file")
            except Exception as e:
                last = e
            # a truncated file must not be mistaken for a cached hit next time
            try:
                if os.path.exists(dest):
                    os.remove(dest)
            except OSError:
                pass
            if attempt + 1 < retries:
                time.sleep(0.5 * (attempt + 1))
        raise last

# Seconds the grid waits for the sources before it draws. Measured 2026-11-10 on
# three prompts: 12 of 15 sources answer within 3 s, Met takes up to 15 s,
# OpenVerse 15-34 s and LOC 80-90 s. A source that needs longer keeps searching
# in the background (up to LATE_WAIT) and its results are added when it answers.
SOURCE_WAIT = 8
LATE_WAIT = 150

# Full-size files are fetched ahead only for the first PREFETCH cards (the
# rest load when a card is enlarged or approved): fetching all of them put
# 462 MB in cache/ after one "tiger" search. At start-up the oldest cache
# files are removed until the folder is under CACHE_LIMIT bytes.
PREFETCH = 24
CACHE_LIMIT = 300_000_000

def trim_cache(folder=None, limit=None):
    """Delete the oldest files in cache/ until it holds at most `limit` bytes.
    Returns (files removed, bytes left)."""
    folder = folder or CACHE
    limit = CACHE_LIMIT if limit is None else limit
    files = []
    try:
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                files.append((os.path.getmtime(p), os.path.getsize(p), p))
    except OSError:
        return 0, 0
    total = sum(f[1] for f in files)
    removed = 0
    for _mtime, size, p in sorted(files):
        if total <= limit:
            break
        try:
            os.remove(p)
            total -= size
            removed += 1
        except OSError:
            pass
    return removed, total

TIME_CHOICES = ["13th century", "14th century", "15th century", "16th century",
                "17th century", "18th century", "19th century", "20th century",
                "21st century"]

def hide_mismatches(items):
    """Split validated items into (shown, hidden_count). Mismatches never display."""
    shown = [it for it in items if it.get("validation", {}).get("verdict") != "MISMATCH"]
    return shown, len(items) - len(shown)

def attribution_text(it):
    """Credit line for a result: creator, holding source, date, and rights.
    Keeps proper attribution visible on cards and in exports."""
    rights = it.get("rights") or it.get("license") or ""
    parts = [it.get("creator"), it.get("source"), it.get("date_str"), rights]
    return " · ".join(str(p).strip() for p in parts if str(p or "").strip())


def split_results(shown, cap=200):
    """Split ranked, on-topic items into (grid, overflow). The grid shows the
    top `cap` (100 per prompt); overflow holds validated extras so a dismissed
    card's slot can be refilled without re-querying."""
    return shown[:cap], shown[cap:]

# Records that are an object NAMED after the subject, not a picture of it: a
# search for "ice cream" brings back ice cream plates, cups and pails. They are
# not hidden, only sorted below the pictures (see off_target).
OBJECT_MEDIA = ("ceramic", "porcelain", "earthenware", "stoneware", "faience",
                "glass", "silver", "pewter", "metalwork", "enamel", "furniture",
                "textile", "decorative art")
OBJECT_NOUNS = {"plate", "dish", "cup", "pail", "spoon", "fork", "knife", "mold",
                "mould", "freezer", "cooler", "slicer", "pitcher", "jug", "pot",
                "bowl", "saucer", "bucket", "vase", "tray", "service", "lid",
                "liner", "box", "jar", "bottle", "chest"}

def off_target(it, brief):
    """Why a record that passed the validator still sorts last, or "".
    Two plain rules, both read from the record's own text:
      1. a prompt of two or more words wants all of them ("ice cream", not
         "Ice Skaters" or "Cream Pot");
      2. an object named after the subject is not a picture of it: the prompt
         is followed by an object word ("Ice Cream Plate"), or the medium is
         an object material (porcelain, silver, glass...).
    Rule 2 is off when the prompt itself names an object or a material."""
    from validator import _canon
    keys = [_canon(k) for k in keywords((brief or {}).get("title", "") or "", cap=6)]
    if not keys:
        return ""
    title = (it.get("title") or "").lower()
    medium = str(it.get("medium") or "").lower()
    words = [_canon(w) for w in re.findall(r"[a-z']{3,}", title)]
    hay = set(words) | {_canon(w) for w in re.findall(
        r"[a-z']{3,}", medium + " " + (it.get("creator") or "").lower())}
    if len(keys) > 1 and not all(k in hay for k in keys):
        return "has only part of the prompt"
    if any(k in OBJECT_NOUNS or any(k in m for m in OBJECT_MEDIA) for k in keys):
        return ""
    for i, w in enumerate(words[:-1]):
        if w == keys[-1] and words[i + 1] in OBJECT_NOUNS:
            return "object named after the subject"
    if any(m in medium for m in OBJECT_MEDIA):
        return "object, not a picture"
    return ""

def rank_key(it, brief=None):
    """Sort key: verdict band first, then fit-quality signals within the band.
    Approved items (and items whose source/medium correlate with approvals)
    get a boost. Validator-passing-but-weak items sort below genuinely-fitting
    ones, so dismissal and refill deal with the weakest last."""
    v = it.get("validation", {})
    band = {"FITS": 0, "PRE": 1, "POST": 1, "UNKNOWN": 2}.get(v.get("verdict"), 9)
    reason = v.get("reason", "")
    extra = str(it.get("extra") or "")
    if "place match" in reason:
        place = 0
    elif "place unverified" in reason:
        place = 1
    else:
        place = 2
    variant = 1 if "via variant" in extra else 0
    backfill = 1 if "date from title/text" in reason else 0
    # weighted feedback: boost sources/media the user has approved before
    boost = 0
    try:
        src = it.get("_src") or it.get("source")
        med = (it.get("medium") or it.get("classification") or "").lower()
        if src in getattr(App, "_approved_sources", set()):
            boost -= 1
        if med and med in getattr(App, "_approved_media", set()):
            boost -= 1
    except Exception:
        pass
    approved = -1 if it.get("_approved") else 0
    off = 1 if (brief and off_target(it, brief)) else 0
    return (approved + boost, band, off, place, variant, backfill)

DISMISSED_FILE = os.path.join(BOARD, "dismissed.json")

APPROVED_FILE = os.path.join(BOARD, "approved.json")

def load_approved(path=APPROVED_FILE):
    """Return {prompt_key: set(ids)} of images the user marked as good."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return {k: set(v) for k, v in d.items()
                if isinstance(k, str) and isinstance(v, list)}
    except (OSError, ValueError):
        return {}

def save_approved(store, path=APPROVED_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({k: sorted(v) for k, v in store.items() if v}, f, indent=1)
    except OSError:
        pass

def prompt_key(b):
    """Stable id for 'the same prompt': normalized title/time/location.
    Dismissals are remembered per-prompt AND globally (under '__global__'),
    so a rejected image never reappears under any prompt."""
    return " | ".join([(b.get(k) or "").strip().lower()
                       for k in ("title", "time_period", "location")])

def load_dismissed(path=DISMISSED_FILE):
    """Return {prompt_key: set(ids)}; missing/corrupt file -> {}."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return {k: set(v) for k, v in d.items()
                if isinstance(k, str) and isinstance(v, list)}
    except (OSError, ValueError):
        return {}

def save_dismissed(store, path=DISMISSED_FILE):
    """Persist {prompt_key: set(ids)}; failures are silent (never block UI)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({k: sorted(v) for k, v in store.items() if v}, f, indent=1)
    except OSError:
        pass

_SEARCH_CACHE = {}          # (source, query, limit, brief_json) -> item list
_CACHE_LOCK = threading.Lock()

def _brief_sig(b):
    """Stable signature of a brief, used inside every session-cache key."""
    try:
        return json.dumps(b, sort_keys=True)
    except TypeError:
        return repr(sorted((b or {}).items()))

def _cache_key(name, vq, lim, b):
    """Session-cache key: identical source+query+budget+brief reuses adapter
    output, so repeat searches (same prompt, post-dismissal) skip the network."""
    return (name, vq, lim, _brief_sig(b))

def _cache_get(key):
    with _CACHE_LOCK:
        hit = _SEARCH_CACHE.get(key)
    return copy.deepcopy(hit) if hit is not None else None

def _cache_put(key, items):
    with _CACHE_LOCK:
        _SEARCH_CACHE[key] = copy.deepcopy(items)
        while len(_SEARCH_CACHE) > 300:  # session-sized, never grows unbounded
            _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))

def merge_plans(plan, got, primary):
    """Pure per-source merge. plan=[(query, limit)...] with plan[0] the primary;
    got={query: (items, err)}. Primary-first, deduped by id, capped at 2x the
    primary budget; fallback hits labeled `via variant`. Errors surface only
    when nothing was retrieved (joined) or every query failed (last one)."""
    seen, merged, errs = set(), [], []
    for vq, _lim in plan:
        items, err = got.get(vq, ([], None))
        if err:
            errs.append(err)
        for it in items:
            if it.get("id") not in seen:
                seen.add(it.get("id"))
                if vq != primary and "via variant" not in str(it.get("extra", "")):
                    it["extra"] = (str(it.get("extra", "")) + f" | via variant '{vq}'").strip(" |")
                merged.append(it)
    budget = plan[0][1]
    merged = merged[:budget * 2]
    if not merged:
        err = "; ".join(errs) if errs else None
    elif len(errs) < len(plan):
        err = None
    else:
        err = errs[-1]
    return merged, err

def _dupe_key(it):
    """Strict cross-source duplicate key, or None when the record is too thin
    to judge (dateless, anonymous, untitled/generic). Same work catalogued by
    two sources shares creator + focused date + substantial title."""
    creator = (it.get("creator") or "").strip().lower()
    if not creator:
        return None
    title = " ".join((it.get("title") or "").lower().split())
    if len(title) < 10 or title.startswith(("untitled", "unknown")):
        return None
    years = parse_years(it.get("date_str") or "")
    if not years or len(years) > 12:
        return None
    return (creator, min(years), max(years), title)

def _phash(img, size=8):
    """Perceptual hash (average hash) using only Pillow: downscale to size x
    size, threshold at the mean. Returns an int bitmask; near-duplicate images
    produce hashes within a small Hamming distance."""
    try:
        g = img.convert("L").resize((size, size))
        px = list(g.getdata())
        mean = sum(px) / len(px)
        bits = 0
        for i, v in enumerate(px):
            if v >= mean:
                bits |= (1 << i)
        return bits
    except Exception:
        return None

def _hamming(a, b):
    return bin(a ^ b).count("1")

# Two previews are "the same picture" when their 16x16 hashes differ by at
# most this many of 256 bits. Measured on a "tiger" search: one museum's
# picture listed by two catalogues differs by 0-2 bits, the closest pair of
# different pictures by 4.
PIC_BITS = 2

def classify_image_type(img):
    """Heuristic photo vs illustration classifier from pixels (no model/deps).
    Returns 'photograph', 'illustration', or 'unknown'. Based on edge density,
    colour variance and saturation distribution."""
    try:
        g = img.convert("L")
        px = list(g.getdata())
        n = len(px)
        mean = sum(px) / n
        var = sum((v - mean) ** 2 for v in px) / n
        # edge density via simple 4-neighbour gradient
        w, h = g.size
        edges = 0
        for y in range(1, h):
            for x in range(1, w):
                idx = y * w + x
                gx = abs(px[idx] - px[idx - 1])
                gy = abs(px[idx] - px[idx - w])
                if (gx + gy) > 40:
                    edges += 1
        edge_density = edges / max(1, (w - 1) * (h - 1))
        # saturation
        hsv = img.convert("HSV")
        sats = [p[1] for p in hsv.getdata()]
        sat_mean = sum(sats) / len(sats)
        # photos: wider tonal range, lower edge density, moderate saturation
        # illustrations: flat colours, high edge density, high saturation
        if edge_density > 0.18 and sat_mean > 90:
            return "illustration"
        if var > 1500 and edge_density < 0.12:
            return "photograph"
        # written letters/words on paper: mostly white background with dark text
        white_ratio = sum(1 for v in px if v > 230) / n
        if white_ratio > 0.55 and edge_density > 0.05 and sat_mean < 40:
            return "document"
        return "unknown"
    except Exception:
        return "unknown"

# Visual descriptors the LLM would normally generate; kept as a local
# synonym/visual-expansion map so the tool stays offline-capable.
VISUAL_SYNONYMS = {
    "bar": ("dimly lit interior", "wooden counter", "bottles", "glasses",
            "patrons", "tavern", "pub scene", "drinking establishment"),
    "portrait": ("face", "head and shoulders", "sitter", "likeness",
                 "frontal view", "bust", "profile"),
    "street": ("urban scene", "buildings", "pedestrians", "cobblestones",
               "carriages", "shopfronts"),
    "church": ("steeple", "nave", "stained glass", "pews", "altar",
               "spire", "religious building"),
    "woman": ("female figure", "lady", "gown", "dress", "bonnet"),
    "man": ("male figure", "gentleman", "suit", "coat", "hat"),
    "child": ("young figure", "boy", "girl", "infant"),
    "interior": ("room", "indoor scene", "domestic", "furniture"),
    "landscape": ("outdoor scene", "countryside", "sky", "horizon", "trees"),
    "battle": ("combat", "soldiers", "weapons", "conflict", "warfare"),
    "market": ("vendors", "stalls", "crowd", "commerce", "goods"),
}

def expand_query_terms(b):
    """Met-style query expansion: turn the brief into concrete visual
    descriptors. Offline (rule-based); an LLM can replace this later."""
    title = (b.get("title") or "").lower()
    loc = (b.get("location") or "").lower()
    toks = re.findall(r"[a-z']{3,}", title + " " + loc)
    out = []
    for t in toks:
        for v in VISUAL_SYNONYMS.get(t, ()):
            if v not in out:
                out.append(v)
    return out

def negative_terms(b):
    """Extract negative cues from the brief/exclude list for filtering."""
    excl = b.get("exclude") or []
    out = []
    for e in excl:
        for w in re.findall(r"[a-z']{3,}", str(e).lower()):
            if w not in out:
                out.append(w)
    return out

def suggest_terms(b):
    """'Did you mean' suggestions derived from the synonym + visual maps."""
    from validator import SYNONYMS
    title = (b.get("title") or "").lower()
    toks = re.findall(r"[a-z']{3,}", title)
    sugg = []
    for t in toks:
        for s in SYNONYMS.get(t, ()):
            if s not in sugg and s != t:
                sugg.append(s)
        for v in VISUAL_SYNONYMS.get(t, ()):
            if v not in sugg:
                sugg.append(v)
    return sugg[:8]

def _dupe_key(it):
    """Strict cross-source duplicate key, or None when the record is too thin
    to judge (dateless, anonymous, untitled/generic). Same work catalogued by
    two sources shares creator + focused date + substantial title."""
    creator = (it.get("creator") or "").strip().lower()
    if not creator:
        return None
    title = " ".join((it.get("title") or "").lower().split())
    if len(title) < 10 or title.startswith(("untitled", "unknown")):
        return None
    years = parse_years(it.get("date_str") or "")
    if not years or len(years) > 12:
        return None
    return (creator, min(years), max(years), title)

def dedupe_items(items):
    """Drop lower-ranked cross-source duplicates from a ranked list; the first
    (best-ranked) copy wins. Returns (deduped, dupe_count)."""
    seen, out, dupes = set(), [], 0
    for it in items:
        key = _dupe_key(it)
        if key is None or key not in seen:
            if key is not None:
                seen.add(key)
            out.append(it)
        else:
            dupes += 1
    return out, dupes

def build_search_query(b):
    """Query = keywords of the prompt (title + location only, capped) plus
    Met-style visual descriptors from expand_query_terms (offline synonym/
    visual map). Style/mood words stay out — only concrete visual terms."""
    kws = keywords((b.get("title", "") + " " + b.get("location", "")), cap=6)
    # append up to 2 visual descriptors to broaden retrieval without poisoning
    extra = [w for w in expand_query_terms(b) if w.lower() not in
             {k.lower() for k in kws}][:2]
    kws = kws + extra
    return " ".join(kws) or clean_query(b.get("title", ""))

def build_search_queries(b):
    """Wider retrieval that still matches the prompt: primary query plus
    prompt-faithful variants. Every variant is derived ONLY from the user's
    own Title/Location words (plus validator synonyms like bar->saloon) —
    no style/mood words, no invented terms — so the validator's topicality
    gate still holds. Adapters merge + dedupe across these; mismatches stay
    hidden by hide_mismatches()."""
    from validator import SYNONYMS
    primary = build_search_query(b)
    if not primary:
        return [clean_query(b.get("title", ""))]
    words = primary.split(" ")
    loc_toks = {w.lower() for w in
                re.findall(r"[a-z']{3,}", (b.get("location") or "").lower())}
    queries = [primary]
    # Variant 1: topic-only (drop location tokens) — catches records whose
    # metadata names the subject but not the place; place is still enforced
    # at display time via the validator's place-match note, not the query.
    nolo = " ".join(w for w in words if w.lower() not in loc_toks).strip()
    if nolo and nolo != primary and nolo not in queries:
        queries.append(nolo)
    # Variant 2: period-synonym swap on the first swappable word
    # (e.g. 19th-c. US cataloging calls bars "saloons" — verified LOC gap).
    for i, w in enumerate(words):
        syns = list(SYNONYMS.get(w.lower(), ()))
        if syns:
            swapped = " ".join(words[:i] + [syns[0]] + words[i + 1:])
            if swapped not in queries:
                queries.append(swapped)
            break
    # Variant 3: shortened core (2 longest words) — archives AND every token,
    # so a short core recalls partial-metadata records the full query misses.
    core = " ".join(sorted(words, key=len, reverse=True)[:2])
    if core and core not in queries and core != nolo:
        queries.append(core)
    return queries[:3]

def grid_columns(avail_width, card_min=280):
    """Responsive grid math (pure, tested): how many cards fit side by side."""
    try:
        return max(1, int(avail_width // card_min))
    except (TypeError, ValueError):
        return 3

def _fit_box(Image, im, box=(208, 156)):
    """Letterbox `im` into exactly `box` pixels (never upscaled), centred on the
    card colour. Two previews of any aspect therefore occupy identical space -
    which is what keeps every row at a fixed height while thumbnails stream in."""
    bw, bh = box
    try:
        iw, ih = im.size
    except Exception:
        return Image.new("RGB", box, PS_SURFACE)
    if iw < 1 or ih < 1:
        return Image.new("RGB", box, PS_SURFACE)
    scale = min(bw / iw, bh / ih, 1.0)
    if scale < 0.999:
        im = im.resize((max(1, round(iw * scale)), max(1, round(ih * scale))),
                       Image.LANCZOS)
    out = Image.new("RGB", box, PS_SURFACE)
    out.paste(im, ((bw - im.size[0]) // 2, (bh - im.size[1]) // 2))
    return out

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Production Processor {VERSION}")
        self.geometry("760x980")
        self.minsize(480, 640)  # flexible down to a usable floor, scrollbars below that
        self.configure(background=PS_BG)
        _style(self)
        self.bind("<Map>", lambda _e: _dark_titlebar(self))
        self.after(200, lambda: _dark_titlebar(self))
        logline(f"=== started {VERSION} ===")
        self.brief = {"title": "", "time_period": "", "location": "",
                      "styles": [], "media": ["Photograph", "Painting", "Illustration"],
                      "exclude": []}
        self.results = []          # list of item dicts with validation
        self._overflow = []        # validated extras beyond the grid cap (dismiss refills)
        self.dismissed = set()     # ids rejected for THIS prompt (session + persisted)
        self.dismissed_store = load_dismissed()  # {prompt_key: set(ids)} across sessions
        self.approved_store = load_approved()     # {prompt_key: set(ids)} of good retrievals
        self.approved_ids = set()
        # dismissals also remember the PICTURE, not only the record id: the
        # same image often sits in two catalogues under two ids
        self.dismissed_pics = set()
        for _h in self.dismissed_store.get("__pictures__", ()):
            try:
                self.dismissed_pics.add(int(_h, 16))
            except ValueError:
                pass
        self.img_hashes = {}       # id -> picture hash of the shown preview
        self._searching = False
        self.prompt_key = ""       # prompt_key of the current search
        self.approved, self.toreview = [], []
        self._approved_sources = set()
        self._approved_media = set()
        self._refill_fetching = False
        self.img_queue = queue.Queue()
        self._img_sem = threading.Semaphore(24)  # max concurrent thumb downloads
        self.prog_queue = queue.Queue()
        self.photos = {}           # id -> PhotoImage (keep refs)
        self.img_boxes = {}        # id -> reserved preview box (keeps rows fixed)
        self.img_labels = {}       # id -> preview label (re-letterboxed on resize)
        self.img_types = {}        # id -> pixel-classified type (photo/illustration)
        self._ph_cache = {}        # placeholder PhotoImage per box size
        self._scroll_until = 0.0   # > now while the user drags the scrollbar
        self._resize_pending = False  # set when a layout recompute is deferred by scrolling
        self._wheel_acc = 0        # coalesces rapid wheel/trackpad events
        self.prefetch_gen = 0      # bumped per search; stale prefetchers quit
        self._build_footer()
        # vertical sash layout: brief / results / collections share height with
        # draggable dividers; results absorbs window growth, footer stays fixed
        self.panes = ttk.Panedwindow(self, orient="vertical")
        self.panes.pack(fill="both", expand=True)
        brief_f = self._build_brief(self.panes)
        results_f = self._build_results(self.panes)
        coll_f = self._build_collections(self.panes)
        self.panes.add(brief_f, weight=0)
        self.panes.add(results_f, weight=1)
        self.panes.add(coll_f, weight=0)                     
        try:
            self.panes.pane(brief_f, minsize=200)            
            self.panes.pane(results_f, minsize=120)          
            self.panes.pane(coll_f, minsize=60)              
        except tk.TclError:
            pass
        self._sash_dragging = False
        self.panes.bind("<ButtonPress-1>", lambda e: setattr(self, "_sash_dragging", True))
        self.panes.bind("<ButtonRelease-1>", lambda e: setattr(self, "_sash_dragging", False))
        self.minsize(640, 420)
        self.geometry("980x740")
        threading.Thread(target=trim_cache, daemon=True).start()
        self.after(150, lambda: self._position_sashes())
        self.after(200, self._drain_images)
        self.after(100, self._poll_progress)

    # ---------- layout ----------
    def _build_brief(self, parent):
        outer = ttk.LabelFrame(parent, text="PROJECT BRIEF", padding=0)
        _bc = tk.Canvas(outer, highlightthickness=0, background=PS_BG)
        _bv = ttk.Scrollbar(outer, orient="vertical", command=_bc.yview)
        _bc.configure(yscrollcommand=_bv.set)
        _bc.pack(side="left", fill="both", expand=True)
        _bv.pack(side="right", fill="y")
        f = ttk.Frame(_bc, padding=8)
        _bw = _bc.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda e: self._schedule_resize())
        _bc.bind("<Configure>", lambda e: _bc.itemconfig(_bw, width=e.width))
        self._brief_canvas = _bc
        f.columnconfigure(1, weight=1)
        f.columnconfigure(2, weight=1)
        f.columnconfigure(3, weight=1)
        ttk.Label(f, text="Title:").grid(row=0, column=0, sticky="w")
        self.e_title = ttk.Entry(f, width=52)
        self.e_title.insert(0, self.brief["title"])
        self.e_title.grid(row=0, column=1, columnspan=2, sticky="ew")
        self.v_exact = tk.BooleanVar(value=False)
        # same blue boxed x marker as the media/source toggles
        _ex = tk.Frame(f, bg=PS_BG)
        _ex.grid(row=0, column=3, sticky="w")
        _ex_marker = tk.Label(_ex, text="×" if self.v_exact.get() else " ",
                              bg=PS_FIELD, fg=PS_ACCENT,
                              font=("Segoe UI", 16, "bold"),
                              relief="solid", borderwidth=2,
                              padx=8, pady=2, width=2)
        _ex_marker.pack(side="left", padx=(0, 6))
        _ex_label = tk.Label(_ex, text="Exact phrase", bg=PS_BG, fg=PS_TEXT, font=PS_FONT)
        _ex_label.pack(side="left")
        def _toggle_exact(_e=None):
            self.v_exact.set(not self.v_exact.get())
            _ex_marker.config(text="×" if self.v_exact.get() else " ")
        for _w in (_ex, _ex_marker, _ex_label):
            _w.bind("<Button-1>", _toggle_exact)
        self.e_title.bind("<Return>", lambda _e: self.search_all())
        ttk.Label(f, text="Time Period:").grid(row=1, column=0, sticky="w")
        self.e_time = ttk.Combobox(f, values=TIME_CHOICES, width=28)
        self.e_time.set(self.brief["time_period"])
        self.e_time.grid(row=1, column=1, columnspan=3, sticky="ew")
        ttk.Label(f, text="Location/Culture:").grid(row=2, column=0, sticky="w")
        self.e_loc = ttk.Entry(f, width=32)
        self.e_loc.insert(0, self.brief["location"])
        self.e_loc.grid(row=2, column=1, columnspan=3, sticky="ew")
        ttk.Label(f, text="Style/Mood:").grid(row=3, column=0, sticky="w")
        self.e_styles = ttk.Entry(f, width=52)
        self.e_styles.insert(0, ", ".join(self.brief["styles"]))
        self.e_styles.grid(row=3, column=1, columnspan=3, sticky="ew")
        ttk.Label(f, text="Medium:").grid(row=4, column=0, sticky="w")
        self.v_photo = tk.BooleanVar(value=True); self.v_paint = tk.BooleanVar(value=True); self.v_illus = tk.BooleanVar(value=True)
        # Native ttk checkmarks render black-on-black on this theme, so use an
        # explicit blue selection marker that stays readable.
        def _media_toggle(parent, text, variable, row, column):
            frame = tk.Frame(parent, bg=PS_BG)
            frame.grid(row=row, column=column, sticky="w")
            marker = tk.Label(frame, text="×" if variable.get() else " ",
                              bg=PS_FIELD, fg=PS_ACCENT,
                              font=("Segoe UI", 16, "bold"),
                              relief="solid", borderwidth=2,
                              padx=8, pady=2, width=2)
            marker.pack(side="left", padx=(0, 6))
            label = tk.Label(frame, text=text, bg=PS_BG, fg=PS_TEXT, font=PS_FONT)
            label.pack(side="left")
            def toggle(_event=None):
                variable.set(not variable.get())
                marker.config(text="×" if variable.get() else " ")
            for widget in (frame, marker, label):
                widget.bind("<Button-1>", toggle)
            return frame
        _media_toggle(f, "Photograph", self.v_photo, 4, 1)
        _media_toggle(f, "Painting", self.v_paint, 4, 2)
        _media_toggle(f, "Illustration", self.v_illus, 4, 3)
        ttk.Label(f, text="Exclude:").grid(row=5, column=0, sticky="w")
        self.e_exc = ttk.Entry(f, width=52)
        self.e_exc.insert(0, ", ".join(self.brief["exclude"]))
        self.e_exc.grid(row=5, column=1, columnspan=3, sticky="ew")
        self.b_search = ttk.Button(f, text="Search All Sources", style="Accent.TButton",
                                   command=self.search_all)
        self.b_search.grid(row=6, column=1, columnspan=2, pady=8)
        # per-source selection
        self.source_vars = {}
        src_box = ttk.LabelFrame(f, text="Sources", padding=4)
        src_box.grid(row=8, column=0, columnspan=4, sticky="ew", pady=4)
        def _src_toggle(parent, text, variable, row, col):
            frame = tk.Frame(parent, bg=PS_BG)
            frame.grid(row=row, column=col, sticky="w", padx=4, pady=2)
            marker = tk.Label(frame, text="×" if variable.get() else " ", bg=PS_FIELD, fg=PS_ACCENT,
                              font=("Segoe UI", 16, "bold"), relief="solid", borderwidth=2,
                              padx=8, pady=2, width=2)
            marker.pack(side="left", padx=(0, 6))
            label = tk.Label(frame, text=text, bg=PS_BG, fg=PS_TEXT, font=PS_FONT_SM)
            label.pack(side="left")
            def toggle(_e=None):
                variable.set(not variable.get())
                marker.config(text="×" if variable.get() else " ")
            for w in (frame, marker, label):
                w.bind("<Button-1>", toggle)
        for i, name in enumerate(_adapters().keys()):
            v = tk.BooleanVar(value=True)
            self.source_vars[name] = v
            _src_toggle(src_box, name, v, i // 4, i % 4)
        self.lbl_status = ttk.Label(f, style="Muted.TLabel",
                                    text="Ready. 14 sources. Tip: wrap a phrase in quotes (e.g. \"ice cream\") to require that exact text.",
                                    anchor="w", justify="left", width=80, wraplength=680)
        self.lbl_status.grid(row=7, column=0, columnspan=4, sticky="w")
        self._status_after = None
        self._status_queue = []
        self.lbl_suggest = ttk.Label(f, style="Muted.TLabel", text="", wraplength=700)
        self.lbl_suggest.grid(row=9, column=0, columnspan=4, sticky="w")
        # mouse wheel scrolls the brief pane too
        self._bind_wheel(f, _bc)
        _bc.bind("<MouseWheel>", lambda e, c=_bc: self._wheel(e, c))
        _bc.bind("<Shift-MouseWheel>", lambda e, c=_bc: self._wheel(e, c, True))
        return outer

    def _set_status(self, text):
        """Debounced, slowed status updates so the bar doesn't jitter."""
        self._status_queue.append(text)
        if self._status_after is not None:
            return
        def _drain():
            self._status_after = None
            if self._status_queue:
                self.lbl_status.config(text=self._status_queue[-1])
                self._status_queue = []
        self._status_after = self.after(120, _drain)

    def _build_results(self, parent):
        f = ttk.LabelFrame(parent, text="RESULTS", padding=8)
        self.lbl_count = ttk.Label(f, text="")
        self.lbl_count.pack(anchor="w")
        # progress row drawn on a canvas so sash/resize repaints are gated with
        # the results canvas instead of Tk repainting a ttk.Progressbar
        self.prog_canvas = tk.Canvas(f, height=20, background=PS_SURFACE,
                                     highlightthickness=0, bd=0, relief="flat")
        self.prog_canvas.pack(fill="x", pady=2)
        self._prog_pct = 0
        self._prog_text = ""
        self.prog_canvas.bind("<Configure>", lambda e: self._draw_progress())
        cv_wrap = ttk.Frame(f); cv_wrap.pack(fill="both", expand=True)
        # canvas bg matches the card surface so scroll erases are invisible;
        # bd=0 removes the 2px border that also flickers on redraw
        self.canvas = tk.Canvas(cv_wrap, background=PS_SURFACE, highlightthickness=0,
                                bd=0, relief="flat")
        self._empty_text = self.canvas.create_text(
            12, 12, anchor="nw", text="No results yet.",
            fill=PS_TEXT, font=PS_FONT_SM)
        # The scrollbar commands are proxied so a drag marks the grid as
        # "user is scrolling": while that holds, previews and auto-hides wait
        # (see _drain_images) instead of resizing rows under the viewport.
        vbar = ttk.Scrollbar(cv_wrap, orient="vertical",
                             command=self._scroll_cmd(self.canvas.yview))
        hbar = ttk.Scrollbar(cv_wrap, orient="horizontal",
                             command=self._scroll_cmd(self.canvas.xview))
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
        hbar.pack(side="bottom", fill="x")
        # No embedded window: cards are canvas items, so scrolling only redraws
        # the canvas (no OS-level child-window move -> no flicker).
        self.canvas.bind("<Configure>", lambda e: self._schedule_resize())
        # mouse wheel: vertical scroll (Shift+wheel = horizontal).
        self.canvas.bind("<MouseWheel>", lambda e: self._wheel(e, self.canvas))
        self.canvas.bind("<Shift-MouseWheel>", lambda e: self._wheel(e, self.canvas, True))
        self.result_cards = []   # card ids in display order
        self.card_items = {}     # id -> dict of canvas item ids
        self.card_positions = {} # id -> (x, y) top-left of card
        self._cols = 3
        return f

    def _position_sashes(self):
        try:
            self.panes.sashpos(0, 360)
        except tk.TclError:
            pass

    def _schedule_resize(self):
        # While the user drags/scrolls, grid-frame <Configure> events (the
        # embedded window being repositioned) would otherwise recompute the
        # scrollregion mid-drag -> canvas redraw -> the remaining jitter.
        # Defer the work and flush it once scrolling stops.
        if self._scrolling():
            self._resize_pending = True
            return
        rid = getattr(self, "_resize_after_id", None)
        if rid is not None:
            try:
                self.after_cancel(rid)
            except tk.TclError:
                pass
        self._resize_after_id = self.after(16, self._do_resize)

    def _do_resize(self):
        if getattr(self, "_sash_dragging", False):
            self._resize_after_id = self.after(16, self._do_resize)
            return
        self._resize_after_id = None
        if self._scrolling():
            self._resize_pending = True
            return
        try:
            w = self.canvas.winfo_width()
        except tk.TclError:
            return
        if w != getattr(self, "_last_canvas_w", 0):
            self._last_canvas_w = w
            cols = grid_columns(w)
            if cols != self._cols:
                self._cols = cols
                self._refit_previews()
            self._reposition_cards()
        bc = getattr(self, "_brief_canvas", None)
        if bc is not None:
            try:
                bc.configure(scrollregion=bc.bbox("all"))
            except tk.TclError:
                pass
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass

    def _reposition_cards(self):
        '''Reposition all result cards for the current column count/width.'''
        if not self.result_cards:
            return
        w = self.canvas.winfo_width()
        if w < 50:
            return
        cols = self._cols
        box = self._img_box()
        bw, bh = box
        card_w = bw + 16
        card_h = bh + 112
        gap = 12
        for i, cid in enumerate(self.result_cards):
            row = i // cols
            col = i % cols
            x = 6 + col * (card_w + gap)
            y = 6 + row * (card_h + gap)
            items = self.card_items.get(cid)
            if items:
                cur_x, cur_y = self.card_positions.get(cid, (0, 0))
                dx = x - cur_x
                dy = y - cur_y
                for item in items:
                    try:
                        self.canvas.move(item, dx, dy)
                    except tk.TclError:
                        pass
            self.card_positions[cid] = (x, y)

    def _on_canvas_click(self, event):
        """Handle clicks on canvas items (cards, buttons)."""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x - 1, y - 1, x + 1, y + 1)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("btn_save_"):
                    cid = tag[len("btn_save_"):]
                    it = self._item_for(cid)
                    if it is not None:
                        self.download(it)
                    return
                if tag.startswith("btn_approve_"):
                    cid = tag[len("btn_approve_"):]
                    it = self._item_for(cid)
                    if it is not None:
                        self.collect(it, True)
                    return
                if tag.startswith("btn_dismiss_"):
                    cid = tag[len("btn_dismiss_"):]
                    it = self._item_for(cid)
                    if it is not None:
                        self.dismiss(it)
                    return
                if tag.startswith("img_"):
                    cid = tag[len("img_"):]
                    it = self._item_for(cid)
                    if it is not None:
                        self.enlarge(it)
                    return

    def _item_for(self, cid):
        for it in self.results:
            if str(it.get("id")) == str(cid):
                return it
        return None

    def _reflow(self):
        self._schedule_resize()

    # ---- progress row (canvas-drawn) ----
    def _set_progress(self, pct=None, text=None):
        if pct is not None:
            self._prog_pct = max(0, min(100, int(pct)))
        if text is not None:
            self._prog_text = text
        self._draw_progress()

    def _draw_progress(self):
        c = getattr(self, "prog_canvas", None)
        if c is None:
            return
        try:
            w = c.winfo_width()
            h = c.winfo_height()
            if w <= 1 or h <= 1:
                return
            c.delete("all")
            c.create_rectangle(0, 0, w - 1, h - 1, outline=PS_BORDER, fill=PS_FIELD)
            fw = int((w - 2) * self._prog_pct / 100.0)
            if fw > 0:
                c.create_rectangle(1, 1, 1 + fw, h - 2, outline="", fill=PS_ACCENT)
            c.create_text(6, h // 2, anchor="w", text=self._prog_text,
                          fill=PS_TEXT, font=PS_FONT_SM)
        except tk.TclError:
            pass

    # ---- scroll stability ----
    def _scroll_cmd(self, real):
        """Proxy for a scrollbar's command: note that the user is scrolling,
        then forward unchanged. (Quantisation was tried here but made small
        drags do nothing, so it is removed.)"""
        def cmd(*args):
            self._mark_scrolling()
            try:
                real(*args)
            except tk.TclError:
                pass
        return cmd

    def _mark_scrolling(self, hold=0.3):
        self._scroll_until = time.time() + hold

    def _scrolling(self):
        return time.time() < getattr(self, "_scroll_until", 0.0)

    def _wheel(self, event, canvas, horizontal=False):
        self._mark_scrolling()
        # coalesce rapid wheel/trackpad events (dozens per gesture) into whole
        # 120-unit steps so the canvas is not redrawn on every tick
        acc = getattr(self, "_wheel_acc", 0) + event.delta
        if abs(acc) < 120:
            self._wheel_acc = acc
            return "break"
        steps = int(acc / 120)
        self._wheel_acc = acc - steps * 120
        try:
            if horizontal or (event.state & 0x0001):
                canvas.xview_scroll(-steps, "units")
            else:
                canvas.yview_scroll(-steps, "units")
        except tk.TclError:
            pass
        return "break"

    def _bind_wheel(self, widget, canvas):
        widget.bind("<MouseWheel>", lambda e, c=canvas: self._wheel(e, c))
        widget.bind("<Shift-MouseWheel>", lambda e, c=canvas: self._wheel(e, c, True))
        for child in widget.winfo_children():
            self._bind_wheel(child, canvas)

    def _img_box(self):
        """Reserved preview box for the current grid: one card column minus
        grid/card padding and the label border, 4:3, capped at the 320x240
        thumb. Every preview in a layout is the same size, so a thumbnail
        landing can never change a row height."""
        try:
            w = self.canvas.winfo_width()
            if w < 50:
                w = max(self.winfo_width() - 60, 480)
            cell = (w - 4) / max(1, getattr(self, "_cols", 3) or 3)
            bw = int(cell - 32)   # grid padx 12 + card padding 16 + label border 4
        except Exception:
            bw = 208
        bw = max(120, min(bw, 480))
        return (bw, max(90, min(360, int(round(bw * 3 / 4)))))

    def _placeholder(self, box):
        """Preview-sized blank image, one per box size. Installed the moment a
        card is built, so the row already has its final height before the
        download starts."""
        ph = self._ph_cache.get(box)
        if ph is not None:
            return ph
        try:
            Image, ImageTk = _need_imaging()
            ph = ImageTk.PhotoImage(Image.new("RGB", box, PS_SURFACE))
        except Exception:
            return None
        self._ph_cache[box] = ph
        return ph

    def _refit_previews(self):
        """The card width changed (column count), so re-letterbox every shown
        preview to the new box. Runs in the background off the cached thumbs
        and comes back through the normal image queue."""
        box = self._img_box()
        jobs = []
        for it in self.results:
            _id = it.get("id")
            self.img_boxes[_id] = box
            lbl = self.img_labels.get(_id)
            if lbl is not None and _id in self.photos:
                jobs.append((it, lbl))
        if not jobs:
            return

        def work():
            Image, _ = _need_imaging()
            for it, lbl in jobs:
                fn = os.path.join(CACHE, (it.get("id") or "img").replace("/", "_") + ".thumb.jpg")
                try:
                    if not os.path.exists(fn) or os.path.getsize(fn) < 500:
                        continue
                    im = Image.open(fn).convert("RGB")
                    im.thumbnail((480, 360))
                    self.img_queue.put(("img", it.get("id"), im, lbl))
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()

    def _build_collections(self, parent):
        # Collections panel is intentionally a stub (approvals feed PDF/PSD
        # export directly); the pane below only holds layout space.
        return ttk.LabelFrame(parent, text="COLLECTIONS", padding=8)

    def _build_footer(self):
        f = ttk.Frame(self); f.pack(side="bottom", fill="x", padx=8, pady=8)
        for c in range(4):
            f.columnconfigure(c, weight=1)
        ttk.Button(f, text="Load", command=self.do_load).grid(row=0, column=0, padx=4, sticky="ew")
        ttk.Button(f, text="Save", command=self.do_save).grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(f, text="Export PDF", command=self.do_pdf).grid(row=0, column=2, padx=4, sticky="ew")
        ttk.Button(f, text="Export PSD", command=self.do_psd).grid(row=0, column=3, padx=4, sticky="ew")

    # ---------- brief ----------
    def read_brief(self):
        media = []
        if self.v_photo.get(): media.append("Photograph")
        if self.v_paint.get(): media.append("Painting")
        if self.v_illus.get(): media.append("Illustration")
        title = self.e_title.get().strip()
        # Exact phrase mode: treat the whole title as one quoted phrase
        if self.v_exact.get() and title and not (title.startswith('"') and title.endswith('"')):
            title = '"' + title + '"'
        return {"title": title,
                "time_period": self.e_time.get().strip(),
                "location": self.e_loc.get().strip(),
                "styles": [s.strip() for s in self.e_styles.get().split(",") if s.strip()],
                "media": media,
                "exclude": [s.strip() for s in self.e_exc.get().split(",") if s.strip()]}

    def build_query(self, b):
        return build_search_query(b)

    # ---------- search ----------
    def search_all(self):
        if self._searching:
            return
        b = self.read_brief()
        self.brief = b
        q = self.build_query(b)
        if not q.strip():
            self._set_status(text="Type a Title (and optionally Time/Location) first, then Search.")
            return
        if not any(v.get() for v in self.source_vars.values()):
            self._set_status(text="Select at least one source in the Sources panel.")
            return
        n_sel = sum(1 for v in self.source_vars.values() if v.get())
        self._set_status(text=f"Searching {build_search_queries(b)} across {n_sel} source(s)…")
        sugg = suggest_terms(b)
        self.lbl_suggest.config(text=("Suggestions: " + ", ".join(sugg)) if sugg else "")
        self.b_search.config(state="disabled")
        self._searching = True
        for cid in list(self.card_items.keys()):
            for item in self.card_items[cid]:
                try:
                    self.canvas.delete(item)
                except tk.TclError:
                    pass
        self.card_items.clear()
        self.card_positions.clear()
        self.results = []
        self._overflow = []
        self._refill_fetching = False
        # drop stale thumbnail refs (100-image grids add up across searches);
        # enlarged (_big) refs are kept so open lightboxes survive a research
        self.photos = {k: v for k, v in self.photos.items() if k.endswith("_big")}
        self.prefetch_gen += 1  # cancel any previous search's full-file prefetcher
        self._search_gen = getattr(self, "_search_gen", 0) + 1  # late answers for an older search are dropped
        # seed this prompt's rejection memory: ids dismissed in an earlier
        # session under the same prompt never enter the grid again
        self.prompt_key = prompt_key(b)
        # learning is per-prompt AND global: anything dismissed anywhere is
        # never shown again, under any prompt
        self.dismissed = set(self.dismissed_store.get(self.prompt_key, set()))
        self.dismissed |= set(self.dismissed_store.get("__global__", set()))
        self.approved_ids = set(self.approved_store.get(self.prompt_key, set()))
        if self.dismissed:
            logline(f"BLOCKED {len(self.dismissed)} previously-dismissed for this prompt")
        self.lbl_count.config(text="Searching…")
        self._set_progress(pct=0)
        self._set_progress(text="Searching 0%")
        th = threading.Thread(target=self._search_worker, args=(q, b), daemon=True)
        th.start()

    def _search_worker(self, q, b, append=False):
        """Thread entry point: any unexpected failure must still re-enable the
        Search button and tell the user, never leave the panel stuck."""
        try:
            self._search_worker_job(q, b, append=append)
        except Exception as e:
            logline(f"SEARCH-FAIL {e}")
            try:
                self.after(0, lambda e=e: self._search_failed(e))
            except Exception:
                pass

    def _search_failed(self, e):
        try:
            self.b_search.config(state="normal")
            self._searching = False
            self._set_progress(pct=0)
            self._set_progress(text="")
            self.lbl_count.config(text="Search failed.")
            self._set_status(text=f"Search failed: {str(e)[:200]}")
        except tk.TclError:
            pass

    def _search_worker_job(self, q, b, append=False, late_got=None):
        """late_got={source: {query: (items, err)}} is the second pass of one
        search: answers that arrived after the grid was drawn. They go through
        the same checks and are added to the grid (no new network calls)."""
        logline(f"SEARCH brief={json.dumps(b)[:200]} query={q!r} append={append}"
                + (f" late={sorted(late_got)}" if late_got else ""))
        gen = getattr(self, "_search_gen", 0)
        queries = build_search_queries(b)
        logline(f"QUERIES {queries}")
        # wide-but-faithful: bigger per-source budgets, primary + variants
        # merged per source, validator hides anything off-prompt.
        AD = _adapters()
        names = [n for n in AD if self.source_vars.get(n, None) is None or self.source_vars[n].get()]
        if late_got is not None:
            names = [n for n in names if n in late_got]
        # Pull as many matches as possible: budgets raised so the full pool
        # survives validation/hiding (mismatches still hidden). Cap is applied
        # later only to keep the grid renderable; overflow holds the rest.
        # Absolute maximum recall: generous per-source budgets. Total raw ~2100;
        # shown count is capped below by the grid cap.
        per_source = {"LOC": 150, "Europeana": 150, "NGA": 150, "Met": 150, "Commons": 150,
                      "Cleveland": 120, "AIC": 150, "Wellcome": 150, "Harvard": 150, "OpenVerse": 150,
                      "SMK": 120, "Rijksmuseum": 120, "Mia": 120, "InternetArchive": 120}
        # primary gets the full budget; each variant gets half (still capped by
        # the adapter) so recall widens without one variant drowning the
        # source's native relevance order.
        plans = {n: [(queries[0], per_source.get(n, 4))] +
                    [(v, max(2, per_source.get(n, 4) // 2)) for v in queries[1:]]
                 for n in names}
        tasks = [(n, vq, lim) for n in names for (vq, lim) in plans[n]]
        total = len(tasks)
        errors, done = [], [0]
        bkey = _brief_sig(b)  # brief signature shared by all tasks

        def fetch_one(task):
            name, vq, lim = task
            key = (name, vq, lim, bkey)
            hit = None if append else _cache_get(key)
            if hit is not None:
                return name, vq, hit, None
            try:
                items, err = AD[name](vq, lim, brief=b)
            except Exception as e:
                return name, vq, [], f"{name} [{vq}]: {e}"
            if err:
                return name, vq, items, f"{name} [{vq}]: {err}"
            _cache_put(key, items)  # clean hits only; errors stay live
            return name, vq, items, None

        # one pool over (source, query) pairs: a source's queries run together
        # instead of sequentially, so search time is the slowest single query,
        # not the sum per source. Repeat prompts hit the session cache.
        # The grid no longer waits for the slowest source: after SOURCE_WAIT
        # seconds it draws what has arrived, and the progress row names the
        # sources still out.
        got, slow, futs = {}, [], {}
        if late_got is not None:
            got = late_got
        else:
            out = {}                      # source -> queries not answered yet
            for n, _vq, _lim in tasks:
                out[n] = out.get(n, 0) + 1
            pool = ThreadPoolExecutor(max_workers=20)
            futs = {pool.submit(fetch_one, t): t for t in tasks}
            try:
                for fut in as_completed(futs, timeout=SOURCE_WAIT):
                    name, vq, items, err = fut.result()
                    got.setdefault(name, {})[vq] = (items, err)
                    done[0] += 1
                    out[name] -= 1
                    still = [n for n in names if out.get(n)]
                    pct = int(done[0] / total * 100)
                    msg = f"Searching {pct}% — {len(names) - len(still)}/{len(names)} sources answered"
                    if still:
                        msg += " — waiting on " + ", ".join(still[:4]) + ("…" if len(still) > 4 else "")
                    self.prog_queue.put((pct, msg))
            except _SearchTimeout:
                slow = [n for n in names if out.get(n)]
            pool.shutdown(wait=False)     # slow sources keep running in the background
        results = {}
        for name in names:
            items, err = merge_plans(plans[name], got.get(name, {}), queries[0])
            results[name] = (items, err)
        all_items = []
        for name in names:  # source order kept: native relevance order within bands
            items, err = results[name]
            for it in items:
                it["_src"] = name
                it["rights"] = (it.get("rights") or it.get("license") or it.get("extra") or "").strip()[:160]
                it["_approved"] = it.get("id") in getattr(self, "approved_ids", set())
                it["validation"] = validate(it, b)
            all_items.extend(items)
            if err:
                errors.append(err)
        if slow:   # first in the status line, ahead of the "no API key" notes
            errors.insert(0, f"{', '.join(slow)}: still searching after {SOURCE_WAIT}s — results are added when they answer")
        if slow and not append:
            def _late(slow=tuple(slow)):
                mine = [f for f, t in futs.items() if t[0] in slow]
                _wait_all(mine, timeout=LATE_WAIT)
                if gen != getattr(self, "_search_gen", 0):
                    return                # the user has started another search
                late = {}
                for f in mine:
                    name, vq, _lim = futs[f]
                    if f.done():
                        _n, _vq, items, err = f.result()
                    else:
                        items, err = [], f"{name} [{vq}]: no answer after {SOURCE_WAIT + LATE_WAIT}s"
                    late.setdefault(name, {})[vq] = (items, err)
                try:
                    self._search_worker_job(q, b, append=True, late_got=late)
                except Exception as e:
                    logline(f"LATE-FAIL {e}")
            threading.Thread(target=_late, daemon=True).start()
        # rejection memory: ids dismissed under this prompt (or globally) never
        # return — filtered before ranking so their slots go to fresh results
        n_blocked = 0
        if self.dismissed:
            kept = [it for it in all_items if it.get("id") not in self.dismissed]
            n_blocked = len(all_items) - len(kept)
            all_items = kept
        # block Midjourney (AI-generated) results entirely
        before = len(all_items)
        all_items = [it for it in all_items
                     if "midjourney" not in ((it.get("title") or "") + " " +
                                             (it.get("creator") or "") + " " +
                                             (it.get("source") or "") + " " +
                                             str(it.get("page_url") or "") + " " +
                                             str(it.get("extra") or "")).lower()]
        if len(all_items) < before:
            logline(f"BLOCKED {before - len(all_items)} midjourney result(s)")
        # block written letters/words on paper (documents, manuscripts, correspondence)
        doc_terms = ("letter", "manuscript", "correspondence", "document",
                     "handwritten", "autograph", "epistle", "page of")
        before = len(all_items)
        all_items = [it for it in all_items
                     if not any(t in ((it.get("title") or "") + " " +
                                      str(it.get("medium") or "") + " " +
                                      str(it.get("extra") or "")).lower()
                                for t in doc_terms)]
        if len(all_items) < before:
            logline(f"BLOCKED {before - len(all_items)} document/letter result(s)")
        # negative search: drop records whose title/attr hit an excluded cue
        negs = negative_terms(b)
        if negs:
            before = len(all_items)
            all_items = [it for it in all_items
                         if not any(n in ((it.get("title") or "") + " " +
                                          (it.get("creator") or "") + " " +
                                          str(it.get("medium") or "")).lower()
                                    for n in negs)]
            if len(all_items) < before:
                logline(f"NEGATIVE filtered {before - len(all_items)} via {negs}")
        # rank: Fits first, then Unknown/Pre/Post, fit-quality within bands.
        # Mismatches are hidden, not shown.
        shown, hidden = hide_mismatches(all_items)
        # one pass over the hidden set for the two "why was it hidden" counts
        excl = off = 0
        for it in all_items:
            v = it["validation"]
            if v["verdict"] != "MISMATCH":
                continue
            if v["reason"].startswith("excluded:"):
                excl += 1
            elif v["reason"].startswith("off-topic"):
                off += 1
        shown.sort(key=lambda it: rank_key(it, b))
        # cross-source duplicates (same work in two archives) waste grid slots
        shown, n_dupes = dedupe_items(shown)
        from collections import Counter
        logline(f"DONE shown={len(shown)} blocked={n_blocked} dupes={n_dupes} hidden={hidden} "
                f"verdicts={dict(Counter(i['validation']['verdict'] for i in all_items))} "
                f"errors={'; '.join(errors)[:300]}")
        if append:
            existing = {r.get("id") for r in self.results}
            new_items = [it for it in shown
                         if it.get("id") not in existing
                         and it.get("id") not in self.dismissed]
            if late_got is not None and gen != getattr(self, "_search_gen", 0):
                return
            self._overflow.extend(new_items)
            logline(f"  APPEND {len(new_items)} new candidate(s) to overflow")
            try:
                if late_got is not None:
                    self.after(0, lambda: self._add_late(names, errors))
                else:
                    self.after(0, self._refill)
            except Exception as e:
                logline(f"REFILL-FAIL {e}")
        else:
            self.results, self._overflow = split_results(shown, cap=500)
            for it in self.results:
                logline(f"  SHOW {it['validation']['label']} | {it.get('_src')} | "
                        f"{str(it.get('date_str'))[:14]} | {str(it.get('title'))[:60]}")
            try:
                self.after(0, lambda: self._render_results(errors, hidden, excl, off))
            except Exception as e:
                logline(f"RENDER-FAIL {e}")

    def _poll_progress(self):
        try:
            while True:
                pct, msg = self.prog_queue.get_nowait()
                try:
                    self._set_progress(pct=pct)
                    self._set_progress(text=msg)
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        self.after(100, self._poll_progress)

    def _update_count(self):
        hid = f" ({self.n_hidden} mismatch{'es' if self.n_hidden != 1 else ''} hidden)" if self.n_hidden else ""
        try:
            self.lbl_count.config(text=f"Showing {self.n_shown} results from {', '.join(self.count_srcs)}{hid}")
        except tk.TclError:
            pass

    def _hide_card(self, item_id, reason):
        """Drop a card from the grid (no preview / failed color-era gate)."""
        entry = self.card_of.pop(item_id, None)
        if not entry:
            return
        items, verdict = entry
        kept = [d for d in (self.approved + self.toreview) if d.get("id") == item_id]
        for it in self.results:
            if it.get("id") == item_id:
                it["validation"] = {"verdict": "MISMATCH", "label": "\u2715 Mismatch",
                                    "reason": reason}
                break
        try:
            if kept:
                self.canvas.itemconfig(verdict, text="\u2715 " + reason + " (kept: you approved it)",
                                       fill=PS_VERDICT["MISMATCH"])
            else:
                for item in items:
                    try:
                        self.canvas.delete(item)
                    except tk.TclError:
                        pass
                self.card_items.pop(item_id, None)
                self.card_positions.pop(item_id, None)
                self.result_cards = [c for c in self.result_cards if c != item_id]
                self.results = [r for r in self.results if r.get("id") != item_id]
                self.n_hidden += 1
                self._refill()
                self.n_shown = len(self.results)
                self._update_count()
                if self.n_shown == 0 and not self._overflow:
                    self._empty_box([], from_hide=True)
        except tk.TclError:
            pass

    def _apply_gate(self, item_id):
        """A preview arrived in full color under a pre-color-era brief: hide its card."""
        self._hide_card(item_id, "color photo under a pre-1935 brief — likely modern")

    def _empty_box(self, errors, excl=0, hidden=0, from_hide=False, off=0):
        tips = []
        if excl:
            tips.append(f"{excl} hit(s) were removed by your Exclude list — clear it if you want them back")
        if off:
            tips.append(f"{off} didn't match your prompt words — check Title/Location")
        if hidden - excl - off > 0:
            tips.append(f"{hidden - excl - off} dated outside '{self.brief.get('time_period', '')}' — widen the Time Period")
        if from_hide:
            tips.append("every preview failed to download — check network, then Search again")
        tips.append("broaden the Title to fewer keywords")
        if errors:
            tips.append("some sources errored (see status bar) — retry on your home network")
        if not from_hide:
            msg = " | ".join(errors) if errors else "All sources answered."
            self._set_status(text=msg[:220])
        self._set_status(text="No results to show. " + "; ".join(tips)[:200])
        try:
            if self._empty_text is None:
                self._empty_text = self.canvas.create_text(
                    12, 12, anchor="nw", text="No results yet.",
                    fill=PS_TEXT, font=PS_FONT_SM)
        except (tk.TclError, AttributeError):
            pass

    def _render_results(self, errors, hidden=0, excl=0, off=0):
        self.b_search.config(state="normal")
        self._searching = False
        self._set_progress(pct=100)
        self._set_progress(text="Done 100% - loading previews.")
        srcs = sorted(set(it["_src"] for it in self.results)) or ["—"]
        self.count_srcs = srcs
        self.n_shown, self.n_hidden = len(self.results), hidden
        self.card_of = {}
        self.img_boxes = {}
        self.img_labels = {}
        self.img_types = {}
        self.img_hashes = {}
        self._resize_pending = False
        self.gate_brief = dict(self.brief)
        self.result_cards = []
        self._update_count()
        if not self.results:
            self._empty_box(errors, excl, hidden, off=off)
            return
        try:
            self.canvas.delete(self._empty_text)
            self._empty_text = None
        except tk.TclError:
            pass
        w = self.canvas.winfo_width()
        if w < 50:
            w = max(self.winfo_width() - 60, 480)
        cols = grid_columns(w)
        self._cols = cols
        box = self._img_box()
        bw, bh = box
        card_w = bw + 16
        card_h = bh + 112
        gap = 12
        for i, it in enumerate(self.results):
            row = i // cols
            col = i % cols
            x = 6 + col * (card_w + gap)
            y = 6 + row * (card_h + gap)
            self.result_cards.append(it["id"])
            self._build_card(it, x, y)
        self._schedule_resize()
        self._prefetch_fulls(list(self.results))
        msg = " | ".join(errors) if errors else "All sources OK."
        self._set_status(text=msg[:220])

    def _build_card(self, it, x=0, y=0):
        """Create one result card as canvas items (no embedded window)."""
        box = self._img_box()
        bw, bh = box
        card_w = bw + 16
        card_h = bh + 112
        cid = it.get("id")
        tag = "card_" + str(cid)
        items = []
        bg = self.canvas.create_rectangle(x, y, x + card_w, y + card_h,
                                         fill=PS_SURFACE, outline=PS_BORDER, width=1,
                                         tags=(tag,))
        items.append(bg)
        ph = self._placeholder(box)
        img = self.canvas.create_image(x + 8, y + 8, image=ph, anchor="nw",
                                       tags=("img", "img_" + str(cid), tag))
        if ph is not None:
            self.canvas.itemconfig(img, image=ph)
        items.append(img)
        self.img_boxes[cid] = box
        self.img_labels[cid] = img
        attr = attribution_text(it)
        info = it["_src"] + "\n" + (it.get("title") or "")[:40]
        if attr:
            info += "\n" + attr[:64]
        txt = self.canvas.create_text(x + 8, y + 8 + bh + 4, text=info, anchor="nw",
                                     fill=PS_TEXT, font=PS_FONT_SM, width=card_w - 16,
                                     tags=(tag,))
        items.append(txt)
        # Generous fixed spacing so wrapped text never overlaps the verdict
        # or buttons, regardless of how many lines the title/attr wrap to.
        val = it["validation"]
        symbol = (val.get("label") or "? Unknown").partition(" ")[0]
        vcolor = PS_VERDICT.get(val.get("verdict"), PS_TEXT_2)
        verdict_y = y + 8 + bh + 74
        verdict = self.canvas.create_text(x + 8, verdict_y,
                                          text=(symbol + " - " + val.get("reason", ""))[:70],
                                          anchor="nw", fill=vcolor, font=PS_FONT_SM,
                                          width=card_w - 16, tags=(tag, "verdict"))
        items.append(verdict)
        btn_y = verdict_y + 24
        # Save
        sr = self.canvas.create_rectangle(x + 8, btn_y, x + 58, btn_y + 22,
                                          fill=PS_BTN, outline=PS_BTN_BORDER,
                                          tags=("btn_save", "btn_save_" + str(cid), tag))
        st = self.canvas.create_text(x + 33, btn_y + 11, text="Save", fill=PS_TEXT,
                                     font=PS_FONT_SM, tags=("btn_save", "btn_save_" + str(cid), tag))
        items.extend([sr, st])
        # Approve
        ar = self.canvas.create_rectangle(x + 62, btn_y, x + 88, btn_y + 22,
                                          fill=PS_BTN, outline=PS_BTN_BORDER,
                                          tags=("btn_approve", "btn_approve_" + str(cid), tag))
        at_ = self.canvas.create_text(x + 75, btn_y + 11, text="\u2713", fill=PS_TEXT,
                                     font=PS_FONT_SM, tags=("btn_approve", "btn_approve_" + str(cid), tag))
        items.extend([ar, at_])
        # Dismiss
        dr = self.canvas.create_rectangle(x + 92, btn_y, x + 118, btn_y + 22,
                                          fill=PS_BTN, outline=PS_BTN_BORDER,
                                          tags=("btn_dismiss", "btn_dismiss_" + str(cid), tag))
        dt = self.canvas.create_text(x + 105, btn_y + 11, text="\u2715", fill=PS_TEXT,
                                     font=PS_FONT_SM, tags=("btn_dismiss", "btn_dismiss_" + str(cid), tag))
        items.extend([dr, dt])
        self.card_items[cid] = items
        self.card_positions[cid] = (x, y)
        self.card_of[cid] = (items, verdict)
        self.img_labels[cid] = img
        # reliable click handling via tag_bind
        self.canvas.tag_bind(img, "<Button-1>", lambda e, it=it: self.enlarge(it))
        self.canvas.tag_bind("btn_save_" + str(cid), "<Button-1>", lambda e, it=it: self.download(it))
        self.canvas.tag_bind("btn_approve_" + str(cid), "<Button-1>", lambda e, it=it: self.collect(it, True))
        self.canvas.tag_bind("btn_dismiss_" + str(cid), "<Button-1>", lambda e, it=it: self.dismiss(it))
        self._fetch_thumb(it, img, self.gate_brief)
        return items

    def _regrid(self):
        """Re-position cards in order after a removal (fills the hole, keeps order)."""
        self._reposition_cards()

    def _refill(self):
        """Pull the next validated extra from the overflow buffer into the grid."""
        while self._overflow:
            nxt = self._overflow.pop(0)
            if nxt.get("id") in self.dismissed:
                continue
            if any(r.get("id") == nxt.get("id") for r in self.results):
                continue
            self.results.append(nxt)
            logline(f"  REFILL {nxt['validation']['label']} | {nxt.get('_src')} | "
                f"{str(nxt.get('date_str'))[:14]} | {str(nxt.get('title'))[:60]}")
            items = self._build_card(nxt)
            self.result_cards.append(nxt.get("id"))
            self._regrid()               # fill the hole left by the dismissed card
            self._schedule_resize()
            self.count_srcs = sorted(set(it["_src"] for it in self.results)) or ["—"]
            self._prefetch_fulls([nxt])
            return True
        # overflow empty: try to fetch more candidates in the background so a
        # dismissed slot can still be refilled with a fresh match
        if not getattr(self, "_refill_fetching", False):
            self._refill_fetching = True
            b = dict(self.brief)
            threading.Thread(target=self._refill_fetch, args=(b,), daemon=True).start()
        self._regrid()
        return False

    def _add_late(self, names, errors):
        """A slow source answered after the grid was drawn: add its cards."""
        shown = {r.get("id") for r in self.results}
        added = 0
        while self._overflow and len(self.results) < 500:
            nxt = self._overflow.pop(0)
            if nxt.get("id") in self.dismissed or nxt.get("id") in shown:
                continue
            shown.add(nxt.get("id"))
            self.results.append(nxt)
            self.result_cards.append(nxt.get("id"))
            self._build_card(nxt)
            added += 1
        if added:
            self._regrid()
            self._schedule_resize()
            self.count_srcs = sorted(set(it["_src"] for it in self.results)) or ["—"]
            self.n_shown = len(self.results)
            self._update_count()
            try:
                self.canvas.delete(self._empty_text)
                self._empty_text = None
            except (tk.TclError, AttributeError):
                pass
        msg = f"{', '.join(names)} answered late: {added} more result(s) added."
        if errors:
            msg += " " + " | ".join(errors)
        logline("LATE " + msg[:200])
        self._set_progress(text=f"Done 100% - {msg[:90]}")
        self._set_status(text=msg[:220])

    def _refill_fetch(self, b):
        try:
            q = self.build_query(b)
            self._search_worker_job(q, b, append=True)
        except Exception as e:
            logline(f"REFILL-FETCH-FAIL {e}")
        finally:
            self._refill_fetching = False

    def _remember_dismissed(self, item_id):
        """Record an id as dismissed everywhere (a copy of a dismissed picture)."""
        self.dismissed.add(item_id)
        self.dismissed_store.setdefault("__global__", set()).add(item_id)
        save_dismissed(self.dismissed_store)
        logline(f"DISMISS-COPY {item_id}")

    def dismiss(self, it):
        """✕: drop the card from the grid and refill its slot with the next
        validated result (never a dismissed or already-shown id). The rejection
        is remembered under this prompt, so a repeat search skips it too."""
        item_id = it.get("id")
        self.dismissed.add(item_id)
        self.dismissed_store.setdefault(self.prompt_key, set()).add(item_id)
        # learn globally: this id never comes back under any prompt
        self.dismissed_store.setdefault("__global__", set()).add(item_id)
        # learn the picture itself, so its copy under another id stays away too
        pic = self.img_hashes.pop(item_id, None)
        if pic is not None:
            self.dismissed_pics.add(pic)
            self.dismissed_store.setdefault("__pictures__", set()).add(format(pic, "x"))
        save_dismissed(self.dismissed_store)
        # drop any cached files for the dismissed image so they don't linger
        _base = (item_id or "img").replace("/", "_")
        for _suffix in (".thumb.jpg", ".full"):
            try:
                _fn = os.path.join(CACHE, _base + _suffix)
                if os.path.exists(_fn):
                    os.remove(_fn)
            except Exception:
                pass
        entry = self.card_of.pop(item_id, None)
        if entry:
            items, verdict = entry
            for item in items:
                try:
                    self.canvas.delete(item)
                except tk.TclError:
                    pass
            self.card_items.pop(item_id, None)
            self.card_positions.pop(item_id, None)
        self.result_cards = [c for c in self.result_cards if c != item_id]
        self.results = [r for r in self.results if r.get("id") != item_id]
        logline(f"DISMISS {item_id}")
        self._refill()
        self.n_shown = len(self.results)
        self._update_count()
        if not self.results and not self._overflow:
            self._empty_box([], from_hide=True)

    def _prefetch_fulls(self, items):
        """Idle-download full files after a search so enlarge() is instant.
        A small pool overlaps network waits; bumping prefetch_gen cancels.
        Only the first PREFETCH cards of a grid are fetched ahead; a single
        card (refill, approval) is fetched without cancelling the others."""
        if len(items) > 1:
            self.prefetch_gen += 1
            items = items[:PREFETCH]
        gen = self.prefetch_gen

        def one(it):
            if gen != self.prefetch_gen:
                return
            # speed tier, same file enlarge() wants — originals stay on ↓drag
            url = it.get("large_url") or it.get("image_url") or ""
            if not url:
                return
            fn = os.path.join(CACHE, (it.get("id") or "img").replace("/", "_") + ".full")
            try:
                if not os.path.exists(fn) or os.path.getsize(fn) < 1000:
                    _download(url, fn)
            except Exception:
                pass

        def worker():
            todo = list(items)
            if len(todo) <= 1:
                for it in todo:
                    one(it)
                return
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(one, todo))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- images ----------
    def _fetch_thumb(self, it, label, brief=None):
        Image, _ = _need_imaging()

        def worker():
            with self._img_sem:  # 100-card grids share 12 download slots
                self._fetch_thumb_body(it, label, brief)
        threading.Thread(target=worker, daemon=True).start()

    def _fetch_thumb_body(self, it, label, brief=None):
        Image, _ = _need_imaging()
        url = it.get("large_url") or it.get("image_url") or it.get("thumb_url")
        if not url:
            self.img_queue.put(("img", it["id"], None, label))
            return
        fn = os.path.join(CACHE, (it.get("id") or "img").replace("/", "_") + ".thumb.jpg")
        try:
            if not os.path.exists(fn) or os.path.getsize(fn) < 500:
                _download(url, fn, limit=3_000_000)
            try:
                im = Image.open(fn).convert("RGB")
            except Exception:
                os.remove(fn)  # corrupt cache: re-fetch once, then give up
                # a file over the 3 MB limit is cut short and unreadable, and
                # the same URL would be cut again: take the small one instead
                _download(it.get("thumb_url") or url, fn, limit=3_000_000)
                im = Image.open(fn).convert("RGB")
            # keep a preview-sized copy on disk, not the download (up to 3 MB
            # each: 186 MB of "previews" after one search)
            if os.path.getsize(fn) > 120_000:
                try:
                    small = im.copy()
                    small.thumbnail((640, 480))
                    with _dest_lock(fn):
                        small.save(fn + ".tmp", "JPEG", quality=82)
                        os.replace(fn + ".tmp", fn)
                except Exception:
                    pass   # the larger file still works
            im.thumbnail((480, 360))
            self.img_queue.put(("img", it["id"], im, label))
            if brief and photo_gate(fn, it, brief) == "modern":
                self.img_queue.put(("gate", it["id"], None, None))
        except Exception:
            try:
                os.remove(fn)   # never leave an unreadable preview in cache/
            except OSError:
                pass
            self.img_queue.put(("img", it["id"], None, label))

    def _drain_images(self):
        # Previews are letterboxed to a fixed box, so applying one never
        # changes a row height -> safe to apply even while scrolling.
        # Only auto-hides (no preview / color-gate) collapse rows, so those
        # are deferred until the user stops scrolling.
        Image, ImageTk = _need_imaging()
        try:
            while True:
                msg = self.img_queue.get_nowait()
                if msg[0] == "gate":
                    if self._scrolling():
                        self.img_queue.put(msg)
                        break
                    self._apply_gate(msg[1])
                    continue
                _, _id, im, label = msg
                if im is None:
                    if self._scrolling():
                        self.img_queue.put(msg)
                        break
                    # no preview available: drop the card instead of showing a dead box
                    self._hide_card(_id, "no preview available")
                    continue
                try:
                    # letterbox into the reserved box: identical pixels for every
                    # preview, so applying it never changes the row height
                    ph = ImageTk.PhotoImage(
                        _fit_box(Image, im, self.img_boxes.get(_id)))
                    self.photos[_id] = ph
                    self.canvas.itemconfig(label, image=ph)
                    # the same picture as one dismissed earlier, or as a card
                    # already on the grid under another id: drop this copy
                    pic = _phash(im, 16)
                    if pic is not None:
                        if any(_hamming(pic, d) <= PIC_BITS for d in self.dismissed_pics):
                            self._remember_dismissed(_id)
                            self._hide_card(_id, "same picture as one you dismissed")
                            continue
                        if any(k != _id and _hamming(pic, v) <= PIC_BITS
                               for k, v in self.img_hashes.items()):
                            self._hide_card(_id, "same picture as another result")
                            continue
                        self.img_hashes[_id] = pic
                    # pixel-based type classification + media-toggle enforcement
                    itype = classify_image_type(im)
                    self.img_types[_id] = itype
                    if itype == "photograph" and not self.v_photo.get():
                        self._hide_card(_id, "photo (pixel-classified) excluded by medium toggle")
                        continue
                    if itype == "illustration" and not self.v_illus.get():
                        self._hide_card(_id, "illustration (pixel-classified) excluded by medium toggle")
                        continue
                    if itype == "document":
                        self._hide_card(_id, "written text/document excluded")
                        continue
                except tk.TclError:
                    pass
                except Exception as e:
                    logline(f"PREVIEW-FAIL {_id} {e}")
        except queue.Empty:
            pass
        if getattr(self, "_resize_pending", False) and not self._scrolling():
            self._resize_pending = False
            self._schedule_resize()
        # tick faster while scrolling so deferred hides flush promptly
        self.after(80 if self._scrolling() else 200, self._drain_images)

    # ---------- collections ----------
    def collect(self, it, ok):
        dest = self.approved if ok else self.toreview
        if all(d.get("id") != it.get("id") for d in dest):
            dest.append(it)
        if ok:
            # remember this as a good retrieval for this prompt so future
            # searches rank similar results higher
            item_id = it.get("id")
            self.approved_store.setdefault(self.prompt_key, set()).add(item_id)
            save_approved(self.approved_store)
            self.approved_ids.add(item_id)
            self._prefetch_fulls([it])   # the exports need its full-size file
            # weighted feedback: track approved sources/media for boosting
            src = it.get("_src") or it.get("source")
            if src:
                self._approved_sources.add(src)
            med = (it.get("medium") or it.get("classification") or "").strip().lower()
            if med:
                self._approved_media.add(med)
            entry = self.card_of.get(item_id)
            if entry:
                try:
                    items, verdict = entry
                    self.canvas.itemconfig(verdict, text="✓ approved — saved to board",
                                          fill="#2e7d32")
                except tk.TclError:
                    pass
        self._set_status(text=f"{'Approved' if ok else 'To review'}: {len(dest)} image(s) — export via Export PSD/PDF")

    def refresh_lists(self):
        pass  # no-op: collections panel is a stub; approvals feed PDF/PSD export

    def enlarge(self, it):
        """Click-to-enlarge lightbox: cached thumbnail instantly, full file behind it."""
        top = tk.Toplevel(self)
        top.title((it.get("title") or "image")[:60])
        top.geometry("960x800")
        top.configure(background=PS_BG)
        top.bind("<Map>", lambda _e: _dark_titlebar(top))
        cap = (f"{it.get('title','')}\n"
               f"{attribution_text(it)}\n"
               f"{it['validation']['label']} — {it['validation']['reason']}\n"
               f"Page: {it.get('page_url','')}")
        ttk.Label(top, text=cap, wraplength=900, justify="left", anchor="w",
                  font=PS_FONT_SM, foreground=PS_TEXT_2).pack(fill="x", padx=12, pady=8)
        body = ttk.Label(top, text="Loading…")
        body.pack(expand=True)
        status = ttk.Label(top, text="", style="Muted.TLabel")
        status.pack()
        btns = ttk.Frame(top)
        ttk.Button(btns, text="Approve", style="Accent.TButton",
                   command=lambda: (self.collect(it, True), top.destroy())).pack(side="left", padx=4)
        ttk.Button(btns, text="Save Full", command=lambda: self.download(it)).pack(side="left", padx=4)
        ttk.Button(btns, text="Close", command=top.destroy).pack(side="left", padx=4)
        btns.pack(pady=8)

        # instant: the already-cached thumbnail, enlarged
        Image, _ = _need_imaging()
        state = {"orig": None, "job": None}
        thumb_fn = os.path.join(CACHE, (it.get("id") or "img").replace("/", "_") + ".thumb.jpg")
        try:
            if os.path.exists(thumb_fn):
                state["orig"] = Image.open(thumb_fn).convert("RGB")
                self._show_enlarged(body, top, state["orig"].copy(), it, res=(900, 640))
                status.config(text="preview — full image loading…")
            else:
                body.config(text="Loading full image…")
        except Exception:
            body.config(text="Loading full image…")
        top.bind("<Configure>", lambda _e: self._lightbox_refit(body, top, it, state))

        full_fn = os.path.join(CACHE, (it.get("id") or "img").replace("/", "_") + ".full")

        def worker():
            url = it.get("large_url") or it.get("image_url") or it.get("thumb_url") or ""
            if not url:
                self.after(0, lambda: body.config(text="No image file for this record."))
                return
            try:
                if not os.path.exists(full_fn) or os.path.getsize(full_fn) < 1000:
                    _download(url, full_fn)
                im = Image.open(full_fn).convert("RGB")

                def _got():
                    state["orig"] = im
                    self._lightbox_refit(body, top, it, state)
                    status.config(text="")
                self.after(0, _got)
            except Exception as e:
                err = e
                def _fail():
                    status.config(text="")
                    if os.path.exists(thumb_fn):
                        status.config(text="showing preview (full image failed)")
                    else:
                        body.config(text=f"Full image failed ({err}).\nOpen the page instead:\n{it.get('page_url','')}")
                self.after(0, _fail)
        threading.Thread(target=worker, daemon=True).start()

    def _show_enlarged(self, body, top, im, it, res=(900, 640)):
        _, ImageTk = _need_imaging()
        try:
            im.thumbnail(res)
            ph = ImageTk.PhotoImage(im)
            self.photos[it.get("id") + "_big"] = ph
            body.config(image=ph, text="")
        except tk.TclError:
            try:
                body.config(text="Could not display image.")
            except tk.TclError:
                pass

    def _lightbox_refit(self, body, top, it, state):
        """Re-fit the lightbox image to the current window size (debounced)."""
        if state.get("job"):
            try:
                top.after_cancel(state["job"])
            except tk.TclError:
                return
        def _do():
            state["job"] = None
            orig = state.get("orig")
            if orig is None:
                return
            try:
                w = max(top.winfo_width() - 40, 200)
                h = max(top.winfo_height() - 260, 200)
            except tk.TclError:
                return
            self._show_enlarged(body, top, orig.copy(), it, res=(w, h))
        try:
            state["job"] = top.after(250, _do)
        except tk.TclError:
            pass

    def download(self, it):
        """↓drag: save full image to board/ for Photoshop drag-in."""
        url = it.get("image_url")
        if not url:
            messagebox.showinfo("drag", "No image URL for this item.")
            return
        fn = os.path.join(BOARD, (it.get("id") or "img").replace("/", "_") + ".jpg")
        Image, _ = _need_imaging()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r, open(fn, "wb") as f:
                f.write(r.read(15_000_000))
            # also keep a full copy in cache for PSD export
            cf = os.path.join(CACHE, (it.get("id") or "img").replace("/", "_") + ".full")
            try:
                Image.open(fn).convert("RGB").save(cf, "JPEG")
            except Exception:
                pass
            messagebox.showinfo("drag", f"Saved:\n{fn}\nDrag this file into Photoshop, or use Export PSD+JSX.")
        except Exception as e:
            messagebox.showerror("drag failed", f"{e}\n\nRate-limit/hotlink protection is common — open Page URL instead:\n{it.get('page_url')}")

    # ---------- session ----------
    def do_save(self):
        b = self.read_brief()
        p = filedialog.asksaveasfilename(defaultextension=".json", initialfile="brief.json",
                                         filetypes=[("JSON", "*.json")])
        if p:
            store.save_brief(p, b, self.approved, self.toreview)
            self._set_status(text=f"Saved brief → {p}")

    def do_load(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            d = store.load_brief(p)
            b = d.get("brief", d)
            self.e_title.delete(0, "end"); self.e_title.insert(0, b.get("title", ""))
            self.e_time.set(b.get("time_period", ""))
            self.e_loc.delete(0, "end"); self.e_loc.insert(0, b.get("location", ""))
            self.e_styles.delete(0, "end"); self.e_styles.insert(0, ", ".join(b.get("styles", [])))
            self.e_exc.delete(0, "end"); self.e_exc.insert(0, ", ".join(b.get("exclude", [])))
            self.approved, self.toreview = d.get("approved", []), d.get("to_review", [])
            # re-validate loaded items against this brief
            for it in self.approved + self.toreview:
                it["validation"] = validate(it, b)
            self.refresh_lists()
            self._set_status(text=f"Loaded brief ← {p}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def do_pdf(self):
        items = self.approved + self.toreview or self.results
        if not items:
            messagebox.showinfo("Export", "Nothing to export — search first.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="board.pdf",
                                         filetypes=[("PDF", "*.pdf")])
        if p:
            try:
                store.export_pdf(p, self.read_brief(), items, CACHE)
                self._set_status(text=f"Exported PDF → {p}")
            except Exception as e:
                messagebox.showerror("PDF failed", str(e))

    def do_psd(self):
        items = self.approved + self.toreview or self.results
        if not items:
            messagebox.showinfo("Export", "Nothing to export — search first.")
            return
        # approved images whose full-size file is not in cache/ yet would be
        # left out of the PSD: fetch them first
        for it in self.approved + self.toreview:
            fn = os.path.join(CACHE, (it.get("id") or "img").replace("/", "_") + ".full")
            url = it.get("large_url") or it.get("image_url") or ""
            if url and (not os.path.exists(fn) or os.path.getsize(fn) < 1000):
                try:
                    _download(url, fn, retries=1)
                except Exception as e:
                    logline(f"PSD-FETCH-FAIL {it.get('id')} {e}")
        try:
            psd, jsx = store.export_psd_and_jsx(BOARD, items, CACHE)
            self._set_status(text=f"Board → {BOARD} | attribution.txt + load_in_photoshop.jsx (File > Scripts > Browse in Photoshop)")
            messagebox.showinfo("PSD export",
                f"Saved board folder:\n{BOARD}\n\n- {os.path.basename(psd)} (flattened contact sheet)\n- load_in_photoshop.jsx (run in Photoshop: File > Scripts > Browse)\n- attribution.txt (paste into your PSD credits layer)")
        except Exception as e:
            messagebox.showerror("PSD failed", str(e))

if __name__ == "__main__":
    _ensure_single_instance()
    App().mainloop()
