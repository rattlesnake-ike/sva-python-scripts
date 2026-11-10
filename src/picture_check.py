"""Picture check: does the picture itself show what the prompt asks for?

The sources are searched by their text, so a search for "tiger" also brings
back Tiger Hill landscapes, tiger lilies and a man named Tiger. This module
looks at the preview instead. It runs CLIP (ViT-B/32, 155 MB) on this computer
with onnxruntime: no key, no network after the one download, nothing leaves
the machine.

It is optional. Without the libraries or the model files, score() returns
None and the tool behaves exactly as it did before.

Set up once (installs onnxruntime, numpy, tokenizers; downloads the model
into models/clip/ next to this file):

    python picture_check.py --setup

Try it on any image:

    python picture_check.py tiger some_picture.jpg
"""
import os
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE, "models", "clip")
MODEL_URL = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/"
FILES = {"vision_model_quantized.onnx": "onnx/vision_model_quantized.onnx",
         "text_model_quantized.onnx": "onnx/text_model_quantized.onnx",
         "tokenizer.json": "tokenizer.json"}

# What a picture is compared against: the prompt as a photo, painting, drawing
# and sculpture (the best of the four counts), and ten everyday things it could
# be instead. The score is the prompt's share against those ten, 0 to 1.
KINDS = ("a photo of {}", "a painting of {}", "a drawing of {}", "a sculpture of {}")
OTHERS = ("a landscape", "a building", "a portrait of a person", "a group of people",
          "a flower", "a page of text", "a map", "a household object",
          "an abstract pattern", "an animal")

_lock = threading.Lock()
_state = {}          # loaded sessions, or {"off": reason}
_texts = {}          # phrase -> (prompt vectors, other vectors)


def _load():
    with _lock:
        if _state:
            return
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as e:
            _state["off"] = f"library missing ({e.name})"
            return
        missing = [f for f in FILES if not os.path.exists(os.path.join(MODEL_DIR, f))]
        if missing:
            _state["off"] = "model not downloaded"
            return
        try:
            so = ort.SessionOptions()
            so.intra_op_num_threads = 2
            run = ["CPUExecutionProvider"]
            _state["np"] = np
            _state["vision"] = ort.InferenceSession(
                os.path.join(MODEL_DIR, "vision_model_quantized.onnx"), so, providers=run)
            _state["text"] = ort.InferenceSession(
                os.path.join(MODEL_DIR, "text_model_quantized.onnx"), so, providers=run)
            _state["tok"] = Tokenizer.from_file(os.path.join(MODEL_DIR, "tokenizer.json"))
        except Exception as e:
            _state.clear()
            _state["off"] = f"model did not load ({str(e)[:80]})"


def status():
    """'' when the check can run, otherwise the reason it is off."""
    _load()
    return _state.get("off", "")


def phrase_for(title):
    """The prompt as CLIP should hear it: one countable word gets an article
    ("a tiger"); anything else is used as typed ("ice cream", "tigers")."""
    q = " ".join((title or "").replace('"', " ").split()).lower()
    if q and " " not in q and not q.endswith("s"):
        return ("an " if q[0] in "aeiou" else "a ") + q
    return q


def _text_vec(s):
    np = _state["np"]
    ids = np.array([_state["tok"].encode(s).ids[:77]], dtype=np.int64)
    v = _state["text"].run(None, {"input_ids": ids})[0][0]
    return v / np.linalg.norm(v)


def _image_vec(im):
    from PIL import Image
    np = _state["np"]
    im = im.convert("RGB")
    w, h = im.size
    s = 224 / min(w, h)
    im = im.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BICUBIC)
    w, h = im.size
    left, top = (w - 224) // 2, (h - 224) // 2
    im = im.crop((left, top, left + 224, top + 224))
    a = np.asarray(im, dtype=np.float32) / 255
    a = (a - np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)) \
        / np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
    v = _state["vision"].run(None, {"pixel_values": a.transpose(2, 0, 1)[None]})[0][0]
    return v / np.linalg.norm(v)


def score(im, title):
    """How much the picture looks like the prompt, 0 to 1, or None when the
    check is off or cannot read the picture. `im` is a PIL image or a path."""
    _load()
    if "off" in _state:
        return None
    phrase = phrase_for(title)
    if not phrase:
        return None
    try:
        np = _state["np"]
        if isinstance(im, str):
            from PIL import Image
            im = Image.open(im)
        with _lock:
            if phrase not in _texts:
                if len(_texts) > 50:
                    _texts.clear()
                _texts[phrase] = ([_text_vec(k.format(phrase)) for k in KINDS],
                                  [_text_vec("a picture of " + o) for o in OTHERS])
            mine, others = _texts[phrase]
        v = _image_vec(im)
        logits = np.array([max(float(v @ t) for t in mine)]
                          + [float(v @ t) for t in others]) * 100
        e = np.exp(logits - logits.max())
        return float(e[0] / e.sum())
    except Exception:
        return None


def setup():
    """Install the three libraries and download the model (155 MB), once."""
    import subprocess
    import sys
    import urllib.request
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "onnxruntime", "numpy", "tokenizers"])
    os.makedirs(MODEL_DIR, exist_ok=True)
    for name, remote in FILES.items():
        dest = os.path.join(MODEL_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            print("have", name)
            continue
        print("downloading", name, "...")
        req = urllib.request.Request(MODEL_URL + remote, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(dest + ".part", dest)
    _state.clear()
    print("picture check:", status() or "ready")


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--setup"]:
        setup()
    elif len(sys.argv) >= 3:
        for p in sys.argv[2:]:
            s = score(p, sys.argv[1])
            print(p, "check is off: " + status() if s is None and status() else s)
    else:
        print(__doc__)
