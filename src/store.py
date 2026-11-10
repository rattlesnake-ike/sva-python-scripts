"""Session save/load + board export (PDF contact sheet, layered PSD, Photoshop JSX)."""
import json, os, datetime

def save_brief(path, brief, approved, toreview):
    data = {"brief": brief, "approved": approved, "to_review": toreview,
            "saved": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path

def load_brief(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def export_pdf(path, brief, items, cache_dir="cache"):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    c = canvas.Canvas(path, pagesize=letter)
    W, H = letter
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, H - 40, f"Reference Board: {brief.get('title','')}")
    c.setFont("Helvetica", 10)
    c.drawString(40, H - 58, f"{brief.get('time_period','')} | {brief.get('location','')} | {', '.join(brief.get('styles',[]))}")
    x, y, col_w, th = 40, H - 90, (W - 80) / 3, 150
    col = 0
    for it in items:
        local = os.path.join(cache_dir, (it.get("id") or "img").replace("/", "_") + ".thumb.jpg")
        try:
            if os.path.exists(local):
                c.drawImage(ImageReader(local), x + col * col_w, y - th, col_w - 10, th, preserveAspectRatio=True, anchor="c")
        except Exception:
            pass
        c.setFont("Helvetica", 8)
        tx = x + col * col_w
        c.drawString(tx, y - th - 12, (it.get("source", "") + " " + (it.get("date_str") or ""))[:38])
        c.drawString(tx, y - th - 24, (it.get("validation", {}).get("label", ""))[:38])
        c.drawString(tx, y - th - 36, (it.get("title", "") or "")[:38])
        attr = (it.get("creator", "") or "")[:40]
        c.setFont("Helvetica", 7)
        c.drawString(tx, y - th - 48, attr)
        c.setFont("Helvetica", 6)
        credit = ((it.get("rights") or it.get("source", "") or "") + " " + (it.get("page_url") or ""))[:62]
        c.drawString(tx, y - th - 58, credit)
        col += 1
        if col == 3:
            col = 0
            y -= th + 70
            if y < 120:
                c.showPage()
                y = H - 60
    c.showPage()
    c.save()
    return path

def _layer_name(i, it):
    """Layer name for one board image: number, title, creator, source."""
    parts = [(it.get("title") or "untitled").strip()[:60]]
    for k in ("creator", "source"):
        v = (it.get(k) or "").strip()
        if v:
            parts.append(v[:40])
    return f"{i + 1:02d} " + " | ".join(parts)


def _pack_plane(plane, w, h):
    """PackBits-encode one channel for a PSD: a table of row lengths, then
    the rows. A row of one repeated value (solid alpha, white background)
    shrinks to a few bytes; any other row is stored as it is."""
    import struct
    lens, rows = [], []
    for y in range(h):
        row = plane[y * w:(y + 1) * w]
        out = bytearray()
        if row == row[:1] * w:
            for i in range(0, w, 128):
                n = min(128, w - i)
                out += bytes([257 - n]) + row[:1] if n > 1 else b"\0" + row[:1]
        else:
            for i in range(0, w, 128):
                chunk = row[i:i + 128]
                out += bytes([len(chunk) - 1]) + chunk
        lens.append(len(out))
        rows.append(bytes(out))
    return struct.pack(">H", 1) + struct.pack(f">{h}H", *lens) + b"".join(rows)


def _save_layered_psd(sheet, layers, path):
    """Write an RGB PSD with one layer per image.

    Pillow can read PSD but has no PSD writer (sheet.save(..., "PSD") raises
    KeyError), so emit the standard file directly. `sheet` is the flattened
    picture (what apps without layer support show); `layers` is a list of
    (name, left, top, RGB image), bottom layer first. Every layer has a solid
    alpha channel. Photoshop and Pillow both open it."""
    import struct
    w, h = sheet.size
    records, pixels = [], []
    for name, left, top, im in layers:
        lw, lh = im.size
        short = name.encode("ascii", "replace")[:31]      # legacy name
        pascal = bytes([len(short)]) + short
        pascal += b"\0" * (-len(pascal) % 4)
        uni = name[:255]                                  # full Unicode name
        luni = struct.pack(">I", len(uni)) + uni.encode("utf-16-be")
        luni += b"\0" * (-len(luni) % 2)
        extra = (struct.pack(">I", 0)                     # no layer mask
                 + struct.pack(">I", 0)                   # no blending ranges
                 + pascal
                 + b"8BIM" + b"luni" + struct.pack(">I", len(luni)) + luni)
        data = im.tobytes()
        planes = [_pack_plane(pl, lw, lh) for pl in
                  (b"\xff" * (lw * lh), data[0::3], data[1::3], data[2::3])]
        rec = struct.pack(">iiiiH", top, left, top + lh, left + lw, 4)
        for cid, pl in zip((-1, 0, 1, 2), planes):        # alpha, R, G, B
            rec += struct.pack(">hI", cid, len(pl))
        rec += b"8BIM" + b"norm" + bytes([255, 0, 0, 0])  # opaque, visible
        rec += struct.pack(">I", len(extra)) + extra
        records.append(rec)
        pixels.append(planes)
    info = struct.pack(">h", len(layers)) + b"".join(records)
    info_len = len(info) + sum(len(p) for px in pixels for p in px)
    pad = info_len % 2
    flat = sheet.tobytes()
    with open(path, "wb") as f:
        f.write(struct.pack(">4sH6xHIIHH", b"8BPS", 1, 3, h, w, 8, 3))
        f.write(struct.pack(">I", 0))                     # colour mode data
        f.write(struct.pack(">I", 0))                     # image resources
        f.write(struct.pack(">I", 4 + info_len + pad + 4))  # layer and mask information
        f.write(struct.pack(">I", info_len + pad))        # layer info
        f.write(info)
        for px in pixels:
            for plane in px:
                f.write(plane)
        f.write(b"\0" * pad)
        f.write(struct.pack(">I", 0))                     # no global layer mask
        f.write(struct.pack(">H", 0))                     # flattened picture: raw
        f.write(flat[0::3])                               # red plane
        f.write(flat[1::3])                               # green plane
        f.write(flat[2::3])                               # blue plane


def export_psd_and_jsx(board_dir, items, cache_dir="cache"):
    """Layered PSD (one layer per image, named after it) + a JSX stub."""
    from PIL import Image
    os.makedirs(board_dir, exist_ok=True)
    # pass 1: the cached full images that are actually readable (header-only
    # open, so a 100-item board never decodes 100 images at once)
    found = []
    for it in items:
        p = os.path.join(cache_dir, (it.get("id") or "img").replace("/", "_") + ".full")
        if not os.path.exists(p):
            continue
        try:
            with Image.open(p):
                found.append((it, p))
        except Exception:
            pass
    psd_path = os.path.join(board_dir, "board.psd")
    if found:
        # pass 2: one 800x600 cell per image, three across. Each image keeps
        # its own shape inside the cell and becomes its own layer.
        cols = min(3, len(found))
        rows = (len(found) + 2) // 3
        sheet = Image.new("RGB", (800 * cols, 600 * rows), "white")
        layers = [("Background", 0, 0, sheet.copy())]
        for i, (it, p) in enumerate(found):
            try:
                with Image.open(p) as im:
                    tile = im.convert("RGB")
                tile.thumbnail((800, 600))
                left = (i % 3) * 800 + (800 - tile.size[0]) // 2
                top = (i // 3) * 600 + (600 - tile.size[1]) // 2
                sheet.paste(tile, (left, top))
                layers.append((_layer_name(i, it), left, top, tile))
            except Exception:
                pass
        _save_layered_psd(sheet, layers, psd_path)
    jsx_lines = ['var folder = Folder.selectDialog("Choose board folder");',
                 'if (folder) { var files = folder.getFiles("*.jpg");',
                 'var doc = app.documents.add(2400, 1800, 72, "Reference Board");',
                 'for (var i = 0; i < files.length; i++) {',
                 '  try { var l = doc.artLayers.add(); l.name = files[i].name;',
                 '  var f = File(files[i].fsName); doc.activeLayer = l;',
                 '  // File > Place Embedded equivalent varies by version; fallback opens file:',
                 '  } catch(e) {} } }']
    jsx_path = os.path.join(board_dir, "load_in_photoshop.jsx")
    with open(jsx_path, "w", encoding="utf-8") as f:
        f.write("\n".join(jsx_lines))
    # attribution log
    with open(os.path.join(board_dir, "attribution.txt"), "w", encoding="utf-8") as f:
        for it in items:
            f.write(f"{it.get('title','')} | {it.get('creator','')} | {it.get('source','')} | "
                    f"{it.get('date_str','')} | {it.get('rights','')} | {it.get('page_url','')}\n")
    return psd_path, jsx_path
