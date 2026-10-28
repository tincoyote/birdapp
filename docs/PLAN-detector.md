# Plan: MegaDetector + per-bird AIY at capture (replaces SpeciesNet)

Started 2026-10-20. This file is the hand-off point: if a session runs out of
capacity, the next one reads this, checks the status list, and continues.

## Why
- Measured on the live DB (350 photos since 2026-09-20, 212 named): SpeciesNet
  named 16 photos - 14 squirrels, 2 cats, **zero birds**. AIY on the detector's
  bird crop named 180; James typed 16 custom names.
- SpeciesNet's useful part was its detector (MegaDetector v5a) - it finds each
  animal and its box. Its classifier/ensemble added almost nothing for birds.
- Full-frame AIY confidence does not separate bird/no-bird (measured
  2026-09-07, see AUTO_TRASH comment in main.py). The detector's confidence does.
- run_second_opinion.py only used the FIRST detection (`dets[0]`), so a photo
  with 5 birds got one name.

## Decisions (James, 2026-10-20)
- Drop SpeciesNet classifier. Keep MegaDetector v5a (`md_v5a.0.1.pt`, same file
  SpeciesNet used, sha256 fe3e90e4b1955821ab7c1f88b446dc0c8cb25e109fdd1872916a55305294a5ef,
  280,767,041 bytes). Fallbacks: MDv1000-cedar if NAS too slow, -redwood if
  small birds are missed.
- Run detection on the NAS in the container, as a background worker (never
  blocks the webhook). NAS has 20 GB RAM; image may grow 1-2 GB - OK.
  Laptop benchmark: ~3.5 s/photo (Ryzen 7 5700U). NAS estimate 15-25 s.
- Laptop is almost always on - acceptable fallback runner if needed.
- A photo with 2 House Finches + a Scrub-Jay counts under BOTH species.
  Display can be rough for now ("doesn't need to be perfect").
- Re-run the current photos only (not data/archive).
- Mammals (squirrel/cat/person): quick-pick buttons, no model.
- Detection threshold default 0.2 (MegaDetector's own typical value),
  adjustable in camera_config.json. Manage scores a photo by its best detection.

## Design
- `detections` table: one row per detected animal/person/vehicle per sighting
  (bbox normalized x,y,w,h; det_conf; AIY species/conf on the crop; per-bird
  confirmed name + source).
- `sightings` new columns: detect_status (pending/done/failed), animal_count,
  person_count, max_det_conf, detector_model, detected_at.
- Worker thread in the container: picks newest `pending` first, runs MD, crops
  each animal (+15% margin), runs AIY per crop, writes rows. Photo-level
  species_aiy/confidence_aiy = best animal's AIY (only if not yet confirmed).
- Migration v7 marks every existing sighting `pending` -> backfill happens
  automatically after deploy.
- Species Queue no longer waits for the laptop: a queued photo becomes
  `classified` as soon as detection is done.

## Status
- [x] Benchmark (laptop, 2026-10-20): 3.4-3.5 s/photo, multiple birds found
- [x] Phase 1: schema v7 + aiy.py + detector.py + worker + Dockerfile
- [x] Phase 2: Manage filter (bird count / detector confidence) + bulk reject
- [x] Phase 3: Species Queue per-bird names + Squirrel/Cat/Person buttons
- [x] Phase 4: Gallery confidence/count filter + multi-species
- [x] Phase 5: backfill is automatic (migration v7 marks all photos pending) - VERIFY ON NAS after first deploy
- [x] Phase 6: stats, README/HISTORY/SETUP, SpeciesNet runner -> _Archive, 83 common_names gaps + cat

## Verified 2026-10-20 (cloud test copy of birds.db + 12 real photos)
- Detector on real photos: correct boxes, 2 warblers in one photo each named.
- Webhook -> worker -> 2 detections -> Manage filters; resend re-queues the
  scan; emptying trash removes detections (trigger), no orphans.
- Manage / Species Queue / Gallery / Stats load with no JS errors (headless
  Chromium); per-bird naming, quick buttons, "not a bird", bulk reject with
  stale-count guard all checked.

## Round 2 (2026-10-20 evening, after first NAS run: 16 s/photo, ~105 min backfill)
- Box % : Manage = detector confidence; Species Queue / Gallery / Trash = AIY
  species confidence (people/vehicles always show detector %).
- Exclude any box (bird, person, vehicle): click it or its Exclude button,
  saved immediately (detections.species_confirmed='__ignore__'), counts and
  best-detection recomputed (detector.recompute_summary). Re-scan resets it.
  Motivation: a swinging watering can detected as a person.
- Species Queue: "Species confidence" slider = the LEAST sure bird in the
  photo; sort by the same value.
- Trash: click a thumbnail to view (boxes, arrows, r = restore).

## Round 3 (2026-10-25)
- Manage stage removed from intake: capture -> Species Queue directly
  (main.queue_for_review; startup reconcile moves Manage's backlog in).
- Species Queue: "Bird confidence" slider (max_det_conf) + sort by it.
  Resend keeps the photo in the queue, shown as scanning.
- Manage = Gallery cleanup: species filter, species-confidence slider
  (least sure bird, server-side via main._species_conf_sql), bulk reject /
  send back to Species Queue. Box % on Manage is now AIY's, like Gallery.
- Startup reconcile only moves pending_review strays. It must NOT move
  approved + queued/classified: that's mostly Sept-2026 Gallery photos
  (auto-queued at capture, approved from Manage, marked classified by the
  laptop SpeciesNet run). Caught before deploy.
- Species Queue name box: own picker instead of <datalist> (arrow = full
  list, typed words match anywhere, word-start matches first).
- Vehicles: detector.skip_categories (default ["vehicle"]) - not stored,
  old rows hidden in main._attach_detections.

## 2026-10-26: count_threshold 0.2 -> 0.5, new scans only
- sightings.count_threshold (migration v8) = threshold the photo was
  scanned at; existing scanned photos set to 0.2. Every place that decides
  "counted / listed" uses COALESCE(sightings.count_threshold, config).
  Resend re-scans at the current value.

## 2026-10-27: Manage filters match Species Queue
- Quick-filter buttons replaced by dropdowns: Birds in photo (Any /
  Exactly 1 / 2 or more / None found), Person (Any / yes / no), plus a Bird
  confidence slider and sorts.
- Species confidence follows the Species filter: with a species picked,
  only that species' birds count (main._species_conf_sql(species)).
- Stats species and "2+ birds" links open Manage pre-filtered.

## 2026-10-27 (later): Keep mark + per-species bands
- Keep = sightings.is_favorite (never used before). POST
  /api/sightings/{id}/keep; filter kept=hide|only. Manage hides kept by
  default; k toggles in the preview; "Keep selected". is_favorite no longer
  forces kept photos to the top of every sort.
- Stats species table: 90%+ / 80-89% / <80% / Kept counts per species,
  each linking to Manage pre-filtered (sp_min/sp_max/kept URL params).
- Manage slider top value includes the whole percent (0-92 = under 93%),
  and Manage shows percentages rounded down to match.

## Known follow-ups (not done)
- Species dropdown can list one species twice: once as a bare Latin value
  (unconfirmed AIY guess) and once as a confirmed "Common (Latin)" string.
  Pre-existing; would need the filter to match both forms.
- If the NAS is too slow (Stats shows seconds/photo): set torch_threads 3-4,
  or swap to MDv1000-cedar (~2x faster, 0.991 of v5a accuracy).
- Motion-box left edge firmware bug - report to Thingino maintainer.
- Old /api/sightings/{id}/second-opinion endpoint and classifier_agreement
  column are unused now; left in place, harmless.
