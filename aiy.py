"""Google AIY bird classifier (birds_V1), shared by main.py and detector.py.

Moved out of main.py on 2026-10-20 so the capture path, the resend endpoint
and the new MegaDetector worker thread all use one interpreter. A TFLite
interpreter is NOT thread-safe, and the worker now runs in its own thread
alongside request handlers - hence the lock around every invoke.

Fails soft: if the model or labels are missing, classify() returns
(None, None) and callers treat that as "AIY unavailable", never as junk.
"""
import csv
import logging
import os
import threading

import numpy as np
from PIL import Image

try:  # container
    import tflite_runtime.interpreter as _tflite
    _Interpreter = _tflite.Interpreter
except ImportError:  # laptop venv (ai_edge_litert is tflite's new name)
    from ai_edge_litert.interpreter import Interpreter as _Interpreter

logger = logging.getLogger("birdapp.aiy")

_lock = threading.Lock()
_interp = None
_inp = None
_out = None
labels = {}


def load(model_path, labels_path):
    """Load once at startup. Safe to call again (reloads)."""
    global _interp, _inp, _out
    try:
        interp = _Interpreter(model_path=model_path)
        interp.allocate_tensors()
        new_labels = {}
        with open(labels_path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                try:
                    idx = int(row[0])
                except ValueError:
                    continue  # header row
                new_labels[idx] = row[1] if len(row) > 1 else str(idx)
        with _lock:
            _interp, _inp, _out = interp, interp.get_input_details(), interp.get_output_details()
            labels.clear()
            labels.update(new_labels)
        logger.info("AIY bird model loaded: %d labels, input %s %s",
                    len(labels), _inp[0]["shape"], _inp[0]["dtype"])
    except Exception as e:
        logger.error("Failed to load AIY model (classification will be skipped): %s", e)


def available():
    return _interp is not None


def classify(img):
    """Classify a PIL image (any size/shape). Returns (species, confidence)
    or (None, None) if AIY is unavailable or fails.

    The image is padded to a square with black bars before resizing to the
    model's 224x224 input. Resizing a non-square image straight to a square
    squashes the bird (found 2026-09-21: a 900x400 crop was compressed
    ~2.25x more horizontally than vertically, and AIY said 'background' far
    more often). Padding first makes the resize a uniform scale."""
    if _interp is None:
        return None, None
    try:
        img = img.convert("RGB")
        _, height, width, _ = _inp[0]["shape"]
        w, h = img.size
        side = max(w, h)
        padded = Image.new("RGB", (side, side), (0, 0, 0))
        padded.paste(img, ((side - w) // 2, (side - h) // 2))
        arr = np.array(padded.resize((width, height)))
        dtype = _inp[0]["dtype"]
        if dtype == np.float32:
            data = np.expand_dims(arr.astype(np.float32) / 255.0, axis=0)
        else:
            data = np.expand_dims(arr.astype(dtype), axis=0)
        with _lock:
            _interp.set_tensor(_inp[0]["index"], data)
            _interp.invoke()
            output = _interp.get_tensor(_out[0]["index"])[0]
            out_dtype = _out[0]["dtype"]
            scale, zero_point = _out[0]["quantization"]
        if out_dtype != np.float32:
            output = (output.astype(np.float32) - zero_point) * scale if scale else output.astype(np.float32)
        top = int(np.argmax(output))
        return labels.get(top, f"Unknown (class {top})"), float(output[top])
    except Exception as e:
        logger.exception("AIY classification failed: %s", e)
        return None, None


def classify_file(image_path, crop_box=None):
    """Classify an image file, optionally cropping to crop_box (l, t, r, b) first."""
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            if crop_box:
                img = img.crop(crop_box)
            return classify(img)
    except Exception as e:
        logger.exception("AIY could not open %s: %s", image_path, e)
        return None, None
