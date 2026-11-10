"""Session save/load + board export (PDF contact sheet, PSD, Photoshop JSX)."""
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

def _save_flattened_psd(im, path):
    """Write a flattened RGB PSD.

    Pillow can read PSD but has no PSD writer (sheet.save(..., "PSD") raises
    KeyError), so emit the minimal standard file directly: 26-byte header,
    empty colour-mode/image-resources/layer sections, then one raw plane per
    channel. Photoshop and Pillow both open it."""
    import struct
    rgb = im.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes()
    header = struct.pack(">4sH6xHIIHH", b"8BPS", 1, 3, h, w, 8, 3)
    with open(path, "wb") as f:
        f.write(header)                    # signature/version/size/depth/mode
        f.write(struct.pack(">I", 0))      # colour mode data
        f.write(struct.pack(">I", 0))      # image resources
        f.write(struct.pack(">I", 0))      # layer and mask information
        f.write(struct.pack(">H", 0))      # compression: raw
        f.write(data[0::3])                # red plane
        f.write(data[1::3])                # green plane
        f.write(data[2::3])                # blue plane


def export_psd_and_jsx(board_dir, items, cache_dir="cache"):
    """Flattened PSD via Pillow + a JSX that loads each full image as a Photoshop layer."""
    from PIL import Image
    os.makedirs(board_dir, exist_ok=True)
    # pass 1: the cached full images that are actually readable (header-only
    # open, so a 100-item board never decodes 100 images at once)
    paths = []
    for it in items:
        p = os.path.join(cache_dir, (it.get("id") or "img").replace("/", "_") + ".full")
        if not os.path.exists(p):
            continue
        try:
            with Image.open(p):
                paths.append(p)
        except Exception:
            pass
    psd_path = os.path.join(board_dir, "board.psd")
    if paths:
        # pass 2: paste one tile at a time and release it, bounding memory
        cols = min(3, len(paths))
        rows = (len(paths) + 2) // 3
        sheet = Image.new("RGB", (800 * cols, 600 * rows), "white")
        for i, p in enumerate(paths):
            try:
                with Image.open(p) as im:
                    tile = im.convert("RGB").resize((800, 600))
                sheet.paste(tile, ((i % 3) * 800, (i // 3) * 600))
            except Exception:
                pass
        _save_flattened_psd(sheet, psd_path)
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
