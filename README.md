# Birdapp

A solar-powered Wyze Cam v3 (running [Thingino ](https://github.com/themactep/thingino-firmware)firmware) watches a backyard birdbath, captures motion-triggered photos, finds
every bird in each photo with MegaDetector, names each one with Google's AIY
bird classifier, and has a human confirm the names. Approved sightings show up on a family-facing gallery.

This README covers the **current** architecture only. For the story of how
it got here - abandoned camera builds, power-system failures, and the
lessons learned along the way - see [HISTORY.md](HISTORY.md).

**Birdapp itself doesn't require Thingino, or even a Wyze camera.** The
only actual requirement is something that can POST a JPEG to `/webhook` on
motion - Thingino is just what this particular deployment happens to use.
Any camera with its own motion-triggered upload/webhook feature, a
Raspberry Pi with a camera module, a Home Assistant automation, or
literally anything else capable of an HTTP file upload would work exactly
the same way. See `/webhook` in `main.py` - it only ever reads a multipart
`image` field, nothing Thingino- or Wyze-specific at all.

## How it works

1. The camera detects motion and POSTs a photo to `/webhook`. The photo is
   saved and gets a quick full-frame AIY guess.
2. A background worker in the container (`detector.py`) runs
   [MegaDetector](https://github.com/agentmorris/MegaDetector) v5a on it,
   which finds every animal, person and vehicle and its box.
3. Each animal is cropped out and classified by AIY on its own, so a photo
   with a House Finch pair and a Scrub-Jay gets three names. AIY is far more
   accurate on a crop: on the full frame a bird is only ~17-46 px of AIY's
   224 px input.
4. **Manage**: a human screens bird / no bird, using the detector's result
   to filter ("no bird found", "2+ birds", ...) and to reject or keep every
   match in one click.
5. **Species Queue**: each bird has a row pre-filled with AIY's guess -
   accept, type a correction, mark "not a bird", or one-click Squirrel/Cat
   (AIY only knows birds). Posting approves the photo to the Gallery.
6. Approved sightings appear on `/gallery` (admin) and `/family` (public,
   privacy-cropped, no admin functionality exposed). A photo counts under
   every species in it.

## Review workflow

`Manage` (bird / no bird) → `Species Queue` (name each bird) → `Gallery` (approved) → `/family` (public).

`review_status` (pending_review/approved/rejected) and `species_id_status`
(not_queued/queued/classified/confirmed) are deliberately independent
columns - approving and naming are separate questions. A third,
`detect_status` (pending/done/failed), tracks the detector; `queued` now
just means "sent to Species Queue, detector not finished yet".

## Architecture

**Camera**: this deployment uses a Wyze Cam v3 running [Thingino ](https://github.com/themactep/thingino-firmware)firmware with `prudynt` for motion detection/capture - but as noted above, any motion-triggered image source that can POST to `/webhook` works.

**Power**: solar panel + LiPo battery → Adafruit bq24074 (solar/USB/DC charger with power path management) → Adafruit PowerBoost 500 → camera. Camera framing (classifier crop, public display crop) is tracked in
`camera_config.json`, checked into git since these are calibration values,
not secrets - `prudynt.json`'s motion ROI on the camera itself is a separate
system and must be updated by hand over SSH if the framing ever changes.

**Server**: Synology DS923+ NAS, Docker container (`docker-compose.yml`),
FastAPI + SQLite (`birds.db`). Only `./data` is a live-mounted volume;
application code is baked into the image at build time and needs a rebuild
to take effect, even though editing files on the mapped network share is
immediate.

**Detector**: MegaDetector v5a (the same weights SpeciesNet used) runs on
the NAS CPU inside the container, in one low-priority background thread -
the webhook never waits for it. Settings are in the `detector` section of
`camera_config.json` (threshold, CPU threads); the Stats page shows whether
it's running, its backlog, and seconds per photo. The 281 MB weights file is
downloaded and checksum-verified at image build time. Detections live in
the `detections` table, one row per animal, with its box and its own AIY
name. Until 2026-10-20 a laptop ran SpeciesNet as a second opinion; it named
zero birds in a month, so it was retired - see HISTORY.md and
`docs/PLAN-detector.md`.

## Repo layout

- `main.py` - app setup, core routes, filters, schema migrations
- `aiy.py` - the AIY bird classifier (shared, thread-safe)
- `detector.py` - MegaDetector + per-bird AIY background worker
- `routes/` - `manage.py`, `species_queue.py`, `gallery.py`, `trash.py`
  (admin, HTTP Basic Auth), `public.py` (family + about, unauthenticated),
  `api.py` (shared JSON endpoints), `nav.py` (shared admin nav bar),
  `boxes.py` (shared code that draws detector boxes in the lightboxes),
  `stats.py`
- `migration.py` - idempotent schema migrations, run on every startup
- `camera_config.json` - shared crop-box config (see Architecture above)
- `docs/PLAN-detector.md` - the detector design, decisions and status
- `_Archive/speciesnet-runner/` - the retired laptop SpeciesNet script, kept
  for reference only
- `common_names.csv` - scientific-name &rarr; common-name lookup for AIY's
  species checklist, plus the few mammals named via Species Queue's quick
  buttons

## Tech stack

Python, FastAPI, SQLite, Docker/Docker Compose, Pillow, TFLite (AIY model),
PyTorch + YOLOv5 (MegaDetector, CPU-only), vanilla JS (no frontend
framework - server-rendered HTML with fetch-based actions).

## Links

- [SETUP.md](SETUP.md) - how to actually run this yourself
- [Wyze Cam v3](https://www.wyze.com/products/wyze-cam-v3) - camera hardware
- [Thingino](https://github.com/themactep/thingino-firmware) - firmware
- [Synology](https://www.synology.com/) - NAS running the server
- [MegaDetector](https://github.com/agentmorris/MegaDetector) - finds the birds
- [HISTORY.md](HISTORY.md) - project history and lessons learned

## Acknowledgments

This project builds on models and data from others:

- **[MegaDetector](https://github.com/agentmorris/MegaDetector)** (Dan
  Morris et al.; MIT licence) - finds each animal in a photo. The detection
  code in `detector.py` mirrors SpeciesNet's adaptation of it. Cite:

  ```bibtex
  @article{beery2019efficient,
    title={Efficient Pipeline for Camera Trap Image Review},
    author={Beery, Sara and Morris, Dan and Yang, Siyu},
    journal={arXiv preprint arXiv:1907.06772},
    year={2019}
  }
  ```

- **[SpeciesNet](https://github.com/google/cameratrapai)** (Google) - the
  laptop second classifier until 2026-10-20, and where this project first
  used MegaDetector. If you use SpeciesNet yourself, cite:

  ```bibtex
  @article{gadot2024crop,
    title={To crop or not to crop: Comparing whole-image and cropped classification on a large dataset of camera trap images},
    author={Gadot, Tomer and Istrate, Ștefan and Kim, Hyungwon and Morris, Dan and Beery, Sara and Birch, Tanya and Ahumada, Jorge},
    journal={IET Computer Vision},
    year={2024},
    publisher={Wiley Online Library}
  }
  ```

- **AIY bird classifier** (Google) - names each bird MegaDetector finds.
- **[Ornithophile](https://github.com/tustoz/ornithophile)** (Academic
  Non-Commercial license) - source data for `common_names.csv`, the
  scientific-name-to-common-name lookup AIY's results are displayed through.

## License

[PolyForm Noncommercial 1.0.0](LICENSE) - free to use, modify, and share
for personal, hobby, educational, or nonprofit/government purposes.
Commercial use requires reaching out first.
