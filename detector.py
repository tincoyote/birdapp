"""MegaDetector + per-bird AIY, run in a background worker thread.

Added 2026-10-20 to replace the laptop SpeciesNet step (see
docs/PLAN-detector.md for the measurements behind that decision).

What it does for each photo whose sightings.detect_status = 'pending':
  1. MegaDetector v5a finds every animal / person / vehicle and its box.
  2. Each animal box (+15% margin) is cropped and classified by AIY - one
     species guess per bird, so a photo with a finch pair and a jay gets
     three rows in `detections`, not one name for the whole photo.
  3. Summary columns on `sightings` (animal_count, max_det_conf, ...) are
     filled in for Manage's filters, and the photo-level species_aiy is set
     to the most confidently detected bird's AIY result (unless a human has
     already confirmed the photo - never overwrite a human decision).

The worker never blocks the webhook: capture just inserts the row with
detect_status='pending' and returns. Newest photos are processed first so
fresh arrivals aren't stuck behind the one-time backfill of old photos.

Detection code mirrors SpeciesNet's own detector (speciesnet/detector.py,
itself adapted from github.com/agentmorris/MegaDetector, MIT licence):
same letterbox size/stride, same YOLOv5 NMS and box scaling, same weights.
That's deliberate - it's the exact pipeline whose crops made AIY accurate.
"""
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime

from PIL import Image

import aiy

logger = logging.getLogger("birdapp.detector")

CATEGORY = {1: "animal", 2: "person", 3: "vehicle"}

DEFAULTS = {
    "enabled": True,
    "model_path": "/app/models/md_v5a.0.1.pt",
    "model_name": "MDv5a.0.1",
    # A detection at or above this counts as "a bird is here" (Manage's bird
    # count, per-bird AIY). 0.2 is MegaDetector's own typical threshold.
    "count_threshold": 0.2,
    # Detections between store_threshold and count_threshold are kept in the
    # table (visible as faint boxes) but not counted or classified - so the
    # threshold can be lowered later without re-running everything.
    "store_threshold": 0.1,
    "crop_margin": 0.15,
    "image_size": 1280,
    # CPU threads for PyTorch. The DS923+ has 2 cores / 4 threads, shared
    # with everything else on the NAS - 2 leaves headroom for the web app.
    "torch_threads": 2,
    "idle_poll_seconds": 5,
}

# Live status for the Stats page - written only by the worker thread.
state = {
    "enabled": False, "loaded": False, "model": None, "error": None,
    "processed": 0, "failed": 0, "avg_seconds": None, "last_finished": None,
    "current_id": None,
}


class MegaDetector:
    def __init__(self, model_path, image_size=1280, threads=2):
        import torch
        # Imported here (not at module top) so the web app still starts if
        # PyTorch/yolov5 are missing - detection is then just reported as
        # unavailable on the Stats page.
        from yolov5.utils.augmentations import letterbox
        from yolov5.utils.general import non_max_suppression
        try:
            from yolov5.utils.general import scale_boxes
        except ImportError:
            from yolov5.utils.general import scale_coords as scale_boxes
        self.torch = torch
        self._letterbox, self._nms, self._scale = letterbox, non_max_suppression, scale_boxes
        self.image_size = image_size
        torch.set_num_threads(max(1, int(threads)))
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
        self.model = checkpoint["model"].float().eval()
        for p in self.model.parameters():
            p.requires_grad = False
        # Same compatibility fix SpeciesNet applies for older YOLOv5
        # checkpoints on newer PyTorch.
        for m in self.model.modules():
            if isinstance(m, torch.nn.Upsample) and not hasattr(m, "recompute_scale_factor"):
                m.recompute_scale_factor = None

    def detect(self, img, min_conf):
        """img: PIL RGB. Returns [{category, conf, bbox:[x,y,w,h] normalized}],
        highest confidence first."""
        import numpy as np
        torch = self.torch
        W, H = img.size
        arr = self._letterbox(np.asarray(img), new_shape=self.image_size, stride=64, auto=True)[0]
        t = torch.from_numpy(arr / 255).permute([2, 0, 1]).unsqueeze(0).float()
        with torch.no_grad():
            pred = self.model(t, augment=False)[0]
        res = self._nms(prediction=pred, conf_thres=min_conf)[0]
        out = []
        if len(res):
            res[:, :4] = self._scale(t.shape[2:], res[:, :4], (H, W)).round()
            for x1, y1, x2, y2, conf, cls in res.tolist():
                x1, y1 = max(0.0, x1), max(0.0, y1)
                x2, y2 = min(float(W), x2), min(float(H), y2)
                out.append({
                    "category": CATEGORY.get(int(cls) + 1, "unknown"),
                    "conf": float(conf),
                    "bbox": [x1 / W, y1 / H, (x2 - x1) / W, (y2 - y1) / H],
                })
        out.sort(key=lambda d: d["conf"], reverse=True)
        return out


def crop_detection(img, bbox, margin):
    """Crop a normalized [x, y, w, h] box plus margin on every side."""
    W, H = img.size
    x, y, w, h = bbox
    mx, my = w * margin, h * margin
    box = (max(0, int((x - mx) * W)), max(0, int((y - my) * H)),
           min(W, int((x + w + mx) * W)), min(H, int((y + h + my) * H)))
    return img.crop(box)


def analyze(md, image_path, cfg):
    """Run detector + per-animal AIY on one file. Pure function of the
    image - no DB access - so it can be tested standalone."""
    with Image.open(image_path) as im:
        img = im.convert("RGB")
    dets = md.detect(img, cfg["store_threshold"])
    for d in dets:
        d["species_aiy"], d["confidence_aiy"] = None, None
        if d["category"] == "animal" and d["conf"] >= cfg["count_threshold"]:
            d["species_aiy"], d["confidence_aiy"] = aiy.classify(crop_detection(img, d["bbox"], cfg["crop_margin"]))
    return dets


def save_results(db_path, sighting_id, dets, cfg, common_names, model_name):
    """Replace this sighting's detections and update its summary columns."""
    thr = cfg["count_threshold"]
    animals = [d for d in dets if d["category"] == "animal" and d["conf"] >= thr]
    people = [d for d in dets if d["category"] == "person" and d["conf"] >= thr]
    max_conf = max((d["conf"] for d in dets if d["category"] == "animal"), default=0.0)
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT species_id_status, species_confirmed, species_confirmed_source "
                          "FROM sightings WHERE id = ?", (sighting_id,)).fetchone()
        if row is None:
            return  # deleted (trash emptied) while we were working
        sid_status, confirmed, confirmed_src = row
        cur.execute("DELETE FROM detections WHERE sighting_id = ?", (sighting_id,))
        for i, d in enumerate(dets):
            x, y, w, h = d["bbox"]
            cur.execute(
                """INSERT INTO detections (sighting_id, idx, category, det_conf, x, y, w, h,
                       species_aiy, confidence_aiy, common_name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sighting_id, i, d["category"], d["conf"], x, y, w, h,
                 d["species_aiy"], d["confidence_aiy"],
                 common_names.get(d["species_aiy"]) if d["species_aiy"] else None, now))
        # A human-confirmed photo with exactly one bird: that name is that
        # bird's name. With several birds we can't know which one the human
        # meant, so per-bird names stay as AIY guesses until reviewed.
        if sid_status == "confirmed" and confirmed and len(animals) == 1:
            cur.execute("UPDATE detections SET species_confirmed = ?, species_confirmed_source = ? "
                        "WHERE sighting_id = ? AND category = 'animal' AND det_conf >= ?",
                        (confirmed, confirmed_src, sighting_id, thr))
        sets = ["detect_status = 'done'", "animal_count = ?", "person_count = ?", "max_det_conf = ?",
                "detector_model = ?", "detected_at = ?"]
        params = [len(animals), len(people), max_conf, model_name, now]
        best = next((d for d in animals if d["species_aiy"]), None)
        if best and sid_status != "confirmed":
            sets += ["species_aiy = ?", "confidence_aiy = ?", "common_name = ?"]
            params += [best["species_aiy"], best["confidence_aiy"], common_names.get(best["species_aiy"])]
        # Species Queue used to wait on the laptop SpeciesNet run ('queued'
        # -> 'classified'). Detection is that step now.
        if sid_status == "queued":
            sets.append("species_id_status = 'classified'")
        cur.execute(f"UPDATE sightings SET {', '.join(sets)} WHERE id = ?", params + [sighting_id])
        conn.commit()
    finally:
        conn.close()


IGNORE = "__ignore__"  # detections.species_confirmed value for a box a human excluded


def recompute_summary(cur, sighting_id, thr, common_names):
    """Re-derive a sighting's summary columns from its detections, leaving
    out boxes a human excluded (a swinging watering can the detector calls
    a person, a leaf it calls an animal). Used after a box is excluded or
    re-included, and after Species Queue posts names."""
    rows = cur.execute(
        "SELECT category, det_conf, species_aiy, confidence_aiy, COALESCE(species_confirmed, '') "
        "FROM detections WHERE sighting_id = ? ORDER BY det_conf DESC", (sighting_id,)).fetchall()
    live = [r for r in rows if r[4] != IGNORE]
    animals = [r for r in live if r[0] == "animal" and r[1] >= thr]
    people = [r for r in live if r[0] == "person" and r[1] >= thr]
    max_conf = max((r[1] for r in live if r[0] == "animal"), default=0.0)
    cur.execute("UPDATE sightings SET animal_count = ?, person_count = ?, max_det_conf = ? WHERE id = ?",
                (len(animals), len(people), max_conf, sighting_id))
    best = next((r for r in animals if r[2]), None)
    if best:
        cur.execute("UPDATE sightings SET species_aiy = ?, confidence_aiy = ?, common_name = ? "
                    "WHERE id = ? AND species_id_status != 'confirmed'",
                    (best[2], best[3], common_names.get(best[2]), sighting_id))


def mark_failed(db_path, sighting_id, message):
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        # A queued photo must not sit as "still scanning" forever because its
        # scan failed - move it on so it can at least be named by hand.
        conn.execute("UPDATE sightings SET detect_status = 'failed', detected_at = ?, "
                     "notes = COALESCE(notes || ' | ', '') || ?, "
                     "species_id_status = CASE WHEN species_id_status = 'queued' THEN 'classified' "
                     "ELSE species_id_status END WHERE id = ?",
                     (datetime.now().isoformat(), f"detector: {message}"[:300], sighting_id))
        conn.commit()
    finally:
        conn.close()


def _next_pending(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        return conn.execute("SELECT id, filename FROM sightings WHERE detect_status = 'pending' "
                            "ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()


def _lower_priority():
    # Linux applies nice per thread; PyTorch's worker threads are created
    # by this thread and inherit it. Keeps page loads snappy during backfill.
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except Exception:
        pass


def _worker(db_path, data_dir, cfg, common_names):
    _lower_priority()
    try:
        md = MegaDetector(cfg["model_path"], cfg["image_size"], cfg["torch_threads"])
        state.update(loaded=True, model=cfg["model_name"], error=None)
        logger.info("MegaDetector loaded (%s, %s threads)", cfg["model_name"], cfg["torch_threads"])
    except Exception as e:
        state.update(loaded=False, error=f"load failed: {e}")
        logger.exception("MegaDetector failed to load - photos stay 'pending' until fixed")
        return
    times = []
    while True:
        try:
            nxt = _next_pending(db_path)
        except Exception as e:
            state["error"] = f"db: {e}"
            time.sleep(30)
            continue
        if not nxt:
            state["current_id"] = None
            time.sleep(cfg["idle_poll_seconds"])
            continue
        sighting_id, filename = nxt
        state["current_id"] = sighting_id
        path = os.path.join(data_dir, filename)
        t0 = time.time()
        try:
            if not os.path.isfile(path):
                raise FileNotFoundError("image file missing")
            dets = analyze(md, path, cfg)
            save_results(db_path, sighting_id, dets, cfg, common_names, cfg["model_name"])
            times = (times + [time.time() - t0])[-50:]
            state.update(processed=state["processed"] + 1, avg_seconds=sum(times) / len(times),
                         last_finished=datetime.now().isoformat(timespec="seconds"), error=None)
        except Exception as e:
            logger.exception("Detection failed for sighting %s", sighting_id)
            state.update(failed=state["failed"] + 1, error=f"#{sighting_id}: {e}")
            try:
                mark_failed(db_path, sighting_id, str(e))
            except Exception:
                logger.exception("Could not mark sighting %s failed", sighting_id)
                time.sleep(30)


def load_config(camera_config):
    cfg = dict(DEFAULTS)
    cfg.update(camera_config.get("detector") or {})
    return cfg


def start(db_path, data_dir, cfg, common_names):
    """Start the worker thread (no-op when disabled in camera_config.json)."""
    state["enabled"] = bool(cfg.get("enabled"))
    if not state["enabled"]:
        logger.info("Detector disabled in camera_config.json")
        return None
    t = threading.Thread(target=_worker, args=(db_path, data_dir, cfg, common_names),
                         name="megadetector", daemon=True)
    t.start()
    return t
