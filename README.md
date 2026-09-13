# Birdapp

A solar-powered Wyze Cam v3 (running [Thingino ](https://github.com/themactep/thingino-firmware)firmware) watches a backyard birdbath, captures motion-triggered photos, and
runs them through two independent AI classifiers before a human confirms the
final species. Approved sightings show up on a family-facing gallery.

This README covers the **current** architecture only. For the story of how
it got here - abandoned camera builds, power-system failures, and the
lessons learned along the way - see [HISTORY.md](HISTORY.md).

## How it works

1. The camera detects motion and POSTs a photo to `/webhook`.
2. A local TFLite model ("AIY") classifies the species and confidence.
3. Gating logic decides whether the sighting is worth a second opinion and
   queues it if so.
4. A standalone script (`run_second_opinion.py`, run off-box - see below)
   pulls queued sightings via the API, runs them through [SpeciesNet](https://github.com/google/cameratrapai), and posts results back.
5. A human reviews both classifiers side by side in **Species Queue** and
   picks a winner (or types a correction) - this is what actually approves a sighting to the gallery.
6. Approved sightings appear on `/gallery` (admin) and `/family` (public,
   privacy-cropped, no admin functionality exposed).

## Review workflow

`Manage` (cleanse the incoming feed) → `Species Queue` (compare classifiers, confirm) → `Gallery` (approved) → `/family` (public).

`review_status` (pending_review/approved/rejected) and `species_id_status`
(not_queued/queued/classified/confirmed) are deliberately independent
columns - approving and getting a second opinion are separate questions.

## Architecture

**Camera**: Wyze Cam v3, [Thingino ](https://github.com/themactep/thingino-firmware)firmware, `prudynt` for motion detection/capture.

**Power**: solar panel + LiPo battery → Adafruit bq24074 (solar/USB/DC charger with power path management) → Adafruit PowerBoost 500 → camera. Camera framing (classifier crop, public display crop) is tracked in
`camera_config.json`, checked into git since these are calibration values,
not secrets - `prudynt.json`'s motion ROI on the camera itself is a separate
system and must be updated by hand over SSH if the framing ever changes.

**Server**: Synology DS923+ NAS, Docker container (`docker-compose.yml`),
FastAPI + SQLite (`birds.db`). Only `./data` is a live-mounted volume;
application code is baked into the image at build time and needs a rebuild
to take effect, even though editing files on the mapped network share is
immediate.

**Second classifier**: [SpeciesNet](https://github.com/google/cameratrapai)
runs off-box (a laptop, not the NAS) in its own Python venv, and talks to
birdapp exclusively over its HTTP API - it never opens `birds.db` directly.
This matters: SQLite's file locking is not reliable over a network share,
and keeping the container as the sole writer avoids that entirely. See
`run_second_opinion.py` and `HISTORY.md` for why this shape was chosen.

## Repo layout

- `main.py` - app setup, AIY model loading, core routes, schema migrations
- `routes/` - `manage.py`, `species_queue.py`, `gallery.py`, `trash.py`
  (admin, HTTP Basic Auth), `public.py` (family + about, unauthenticated),
  `api.py` (shared JSON endpoints), `nav.py` (shared admin nav bar)
- `migration.py` - idempotent schema migrations, run on every startup
- `camera_config.json` - shared crop-box config (see Architecture above)
- `common_names.csv` - scientific-name &rarr; common-name lookup for AIY's
  species checklist (birds only - does not cover non-bird SpeciesNet
  detections)

## Tech stack

Python, FastAPI, SQLite, Docker/Docker Compose, Pillow, TFLite (AIY model),
PyTorch/SpeciesNet (external, laptop-side only), vanilla JS (no frontend
framework - server-rendered HTML with fetch-based actions).

## Links

- [Wyze Cam v3](https://www.wyze.com/products/wyze-cam-v3) - camera hardware
- [Thingino](https://github.com/themactep/thingino-firmware) - firmware
- [Synology](https://www.synology.com/) - NAS running the server
- [SpeciesNet](https://github.com/google/cameratrapai) - second classifier
- [HISTORY.md](HISTORY.md) - project history and lessons learned
