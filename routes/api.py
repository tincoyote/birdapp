import os
import sqlite3
from datetime import datetime
from fastapi import APIRouter

router = APIRouter()


@router.patch("/api/sightings/{sighting_id}/review-status")
async def update_review_status(sighting_id: int, body: dict):
    """Update review_status: 'pending_review', 'approved', or 'rejected'.
    Also stamps review_updated_at so trash/gallery can sort by 'most
    recently changed' - critical for finding a just-made mistake fast.

    'pending_review' (Trash's Restore) means "back to Species Queue" since
    2026-10-25, so it goes through main.queue_for_review - otherwise a photo
    restored after being posted would sit in limbo, shown on no page."""
    from main import DB_PATH, queue_for_review
    status = body.get("review_status")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if status == "pending_review":
        queue_for_review(cursor, "id = ?", [sighting_id])
    else:
        cursor.execute(
            "UPDATE sightings SET review_status = ?, review_updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), sighting_id)
        )
    conn.commit()
    conn.close()
    return {"updated": True, "id": sighting_id, "review_status": status}


@router.post("/api/sightings/{sighting_id}/resend-classifier")
async def resend_classifier(sighting_id: int):
    """Re-scan one sighting and send it to Species Queue, from anywhere
    (Species Queue itself, Gallery, Manage).

    Sets detect_status='pending', so the MegaDetector worker re-finds the
    birds and re-runs AIY on each crop (~9-16 s); the full-frame AIY result
    below is just the placeholder until then. The photo shows in Species
    Queue as "still scanning" meanwhile. Until 2026-10-25 this sent the
    photo back to Manage's bird/no-bird screen instead; that stage is gone.
    Increments classification_attempts each time."""
    from main import DB_PATH, DATA_DIR, classify_aiy, compute_agreement, common_names, queue_for_review

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT filename, classification_attempts FROM sightings WHERE id = ?", (sighting_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return {"error": "Sighting not found"}

    filename, prior_attempts = result
    image_path = os.path.join(DATA_DIR, filename)
    species_aiy, confidence_aiy = classify_aiy(image_path)
    common_name = common_names.get(species_aiy) if species_aiy else None
    agreement = compute_agreement(species_aiy, confidence_aiy, None, None)
    new_attempts = (prior_attempts or 0) + 1

    cursor.execute(
        """UPDATE sightings
           SET species_aiy = ?, confidence_aiy = ?, classifier_agreement = ?,
               common_name = ?, classification_attempts = ?, detect_status = 'pending'
           WHERE id = ?""",
        (species_aiy, confidence_aiy, agreement, common_name, new_attempts, sighting_id)
    )
    queue_for_review(cursor, "id = ?", [sighting_id])
    conn.commit()
    conn.close()
    return {
        "id": sighting_id, "species_aiy": species_aiy, "confidence_aiy": confidence_aiy,
        "common_name": common_name, "classification_attempts": new_attempts,
        "review_status": "pending_review", "species_id_status": "queued"
    }


@router.post("/api/sightings/{sighting_id}/queue-species-id")
async def queue_species_id(sighting_id: int):
    """Send a sighting to Species Queue WITHOUT re-scanning it - Manage's
    "back to Species Queue" for a Gallery photo whose name needs fixing.
    It leaves the Gallery until it's posted again. (Resend is the same
    plus a fresh detector run.)

    History: until 2026-10-25 this was Manage's "worth a species ID" button
    for fresh arrivals; new photos now go to Species Queue on their own.
    Earlier fixes still apply: a 'classified' or 'confirmed' photo IS
    requeued (2026-09-12 / 2026-09-20 - a completed photo sent again is a
    deliberate re-review); only a photo already waiting in the queue is a
    no-op."""
    from main import DB_PATH, queue_for_review
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT species_id_status, review_status FROM sightings WHERE id = ?", (sighting_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Sighting not found"}
    current_status, review_status = row
    if review_status == "pending_review" and current_status in ("queued", "classified"):
        conn.close()
        return {"id": sighting_id, "species_id_status": current_status, "already_in_pipeline": True}
    queue_for_review(cursor, "id = ?", [sighting_id])
    cursor.execute("SELECT species_id_status FROM sightings WHERE id = ?", (sighting_id,))
    new_status = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": sighting_id, "species_id_status": new_status, "already_in_pipeline": False}


@router.post("/api/sightings/{sighting_id}/confirm-species")
async def confirm_species(sighting_id: int, body: dict):
    """Write the human's final pick between the two classifiers (or a manual
    override) into species_confirmed - the first and only writer of that
    column since it was added in the schema-v3 migration. Moves
    species_id_status to 'confirmed'.

    Also sets review_status='approved' in the same call - under the revised
    flow, this endpoint IS the Gallery entry point. Manage no longer
    approves anything directly; a photo only reaches the Gallery once a
    human has picked a winning species here. Also stamps review_updated_at
    to match what the existing PATCH /review-status endpoint does, so
    Gallery's 'recently changed' sort still behaves consistently regardless
    of which endpoint actually approved a given photo.

    species_confirmed_source ('aiy'/'sn'/'custom') records which button (or
    the manual override) produced the value, since species_confirmed itself
    is just a string - a button pick and a hand-typed correction are
    otherwise indistinguishable once saved."""
    from datetime import datetime
    from main import DB_PATH

    species_confirmed = body.get("species_confirmed")
    species_confirmed_source = body.get("species_confirmed_source")
    # Optional per-bird names (2026-10-20):
    #   "birds": [{"detection_id": 12, "species_confirmed": "...", "source": "aiy"}, ...]
    # Each named bird is saved on its detections row. The photo-level
    # species_confirmed (what the family page and older views use) defaults
    # to the first bird's name when the caller doesn't send one.
    birds = [b for b in (body.get("birds") or []) if b.get("detection_id") and b.get("species_confirmed")]
    if not species_confirmed and birds:
        species_confirmed = birds[0]["species_confirmed"]
        species_confirmed_source = species_confirmed_source or birds[0].get("source")
    if not species_confirmed:
        return {"error": "species_confirmed is required"}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sightings WHERE id = ?", (sighting_id,))
    if not cursor.fetchone():
        conn.close()
        return {"error": "Sighting not found"}
    for b in birds:
        # sighting_id in the WHERE: a detection id from another photo is ignored
        cursor.execute(
            "UPDATE detections SET species_confirmed = ?, species_confirmed_source = ? "
            "WHERE id = ? AND sighting_id = ?",
            (b["species_confirmed"], b.get("source"), int(b["detection_id"]), sighting_id))
    if birds:
        import detector
        from main import DETECTOR_CONFIG, common_names
        detector.recompute_summary(cursor, sighting_id, DETECTOR_CONFIG["count_threshold"], common_names)

    cursor.execute(
        """UPDATE sightings
           SET species_confirmed = ?, species_confirmed_source = ?,
               species_id_status = 'confirmed',
               review_status = 'approved', review_updated_at = ?
           WHERE id = ?""",
        (species_confirmed, species_confirmed_source, datetime.now().isoformat(), sighting_id)
    )
    conn.commit()
    conn.close()
    return {
        "id": sighting_id, "species_confirmed": species_confirmed,
        "species_confirmed_source": species_confirmed_source,
        "species_id_status": "confirmed", "review_status": "approved"
    }



@router.post("/api/detections/{detection_id}/exclude")
async def exclude_detection(detection_id: int, body: dict):
    """Exclude one box from a photo's results, or put it back.
    Body: {"excluded": true|false}. An excluded box (a swinging watering can
    the detector calls a person, a leaf it calls a bird) is kept but no
    longer counts: the photo's bird/person counts, best-detection % and
    photo-level AIY guess are recomputed without it, so Manage's filters
    and the Gallery stop seeing it. Saved immediately - no "post" needed.
    Re-running detection (Resend) starts the photo fresh."""
    import detector
    from main import DB_PATH, DETECTOR_CONFIG, common_names, _attach_detections
    excluded = bool(body.get("excluded", True))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT sighting_id, species_confirmed FROM detections WHERE id = ?",
                          (detection_id,)).fetchone()
        if not row:
            return {"error": "Detection not found"}
        sid = row["sighting_id"]
        if excluded:
            cur.execute("UPDATE detections SET species_confirmed = ?, species_confirmed_source = 'excluded' "
                        "WHERE id = ?", (detector.IGNORE, detection_id))
        elif row["species_confirmed"] == detector.IGNORE:
            cur.execute("UPDATE detections SET species_confirmed = NULL, species_confirmed_source = NULL "
                        "WHERE id = ?", (detection_id,))
        detector.recompute_summary(cur, sid, DETECTOR_CONFIG["count_threshold"], common_names)
        conn.commit()
        s = dict(cur.execute("SELECT id, animal_count, person_count, max_det_conf, species_aiy, "
                             "confidence_aiy, common_name, detect_status, count_threshold "
                             "FROM sightings WHERE id = ?",
                             (sid,)).fetchone())
        _attach_detections(cur, [s])
        return s
    finally:
        conn.close()


@router.post("/api/sightings/{sighting_id}/second-opinion")
async def second_opinion(sighting_id: int, body: dict):
    """Write a second classifier's result for one sighting. Reuses the
    existing species_inat/confidence_inat columns regardless of which model
    actually produced the result (SpeciesNet as of 2026-09, per the rev8
    decision that the schema shouldn't care which classifier wins). Moves
    species_id_status from 'queued' to 'classified' so /species-queue knows
    to render both classifiers side by side for human review, rather than
    still treating the row as merely pending. This is the only intended
    writer of species_inat/confidence_inat - the SpeciesNet script runs
    off-box (laptop, not this container) and POSTs its result here instead
    of touching birds.db directly, since a second process opening the same
    SQLite file over a network share is not something SQLite's locking
    reliably supports."""
    from main import DB_PATH, compute_agreement

    species_inat = body.get("species_inat")
    confidence_inat = body.get("confidence_inat")
    is_species_level_inat = body.get("is_species_level_inat", True)
    higher_level_match = body.get("higher_level_match")
    # Only meaningful when is_species_level_inat is False - the raw top
    # candidate SpeciesNet's classifier actually favored before its own
    # rollup logic stepped the official prediction back to a coarser
    # label. See migrate_v5_to_v6 for why this is worth keeping at all.
    species_inat_raw_guess = body.get("species_inat_raw_guess")
    confidence_inat_raw = body.get("confidence_inat_raw")
    if species_inat is None:
        return {"error": "species_inat is required"}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT species_aiy, confidence_aiy FROM sightings WHERE id = ?", (sighting_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return {"error": "Sighting not found"}

    species_aiy, confidence_aiy = result
    # Optional AIY re-run on SpeciesNet's detector crop (2026-09-23). The
    # capture-time AIY result runs on the full frame, where the bird is only
    # ~17-46px of AIY's 224px input - it said 'background' or defaulted to
    # 'House Sparrow' on clear House Finch photos. The same model on the
    # detector's bird crop called them correctly at 0.55-0.96. When the
    # runner supplies it, it replaces the full-frame guess outright.
    common_name_update = None
    if body.get("species_aiy") is not None:
        from main import common_names
        species_aiy = body["species_aiy"]
        confidence_aiy = body.get("confidence_aiy")
        common_name_update = common_names.get(species_aiy)
        cursor.execute(
            "UPDATE sightings SET species_aiy = ?, confidence_aiy = ?, common_name = ? WHERE id = ?",
            (species_aiy, confidence_aiy, common_name_update, sighting_id)
        )
    agreement = compute_agreement(
        species_aiy, confidence_aiy, species_inat, confidence_inat,
        is_species_level_inat, higher_level_match
    )

    cursor.execute(
        """UPDATE sightings
           SET species_inat = ?, confidence_inat = ?, classifier_agreement = ?,
               species_id_status = 'classified',
               species_inat_raw_guess = ?, confidence_inat_raw = ?
           WHERE id = ?""",
        (species_inat, confidence_inat, agreement,
         species_inat_raw_guess, confidence_inat_raw, sighting_id)
    )
    conn.commit()
    conn.close()
    return {
        "id": sighting_id, "species_inat": species_inat, "confidence_inat": confidence_inat,
        "classifier_agreement": agreement,
        "species_inat_raw_guess": species_inat_raw_guess, "confidence_inat_raw": confidence_inat_raw
    }


@router.post("/api/trash-review/empty")
async def empty_review_trash():
    """Permanently delete review_status='rejected' sightings + their image files.
    Separate from the legacy /api/trash/empty (which uses is_trashed) so the
    old endpoint stays untouched while this one drives the new workflow.

    Commits after EACH row rather than once at the end, and isolates each
    row in its own try/except. Filesystem deletes aren't transactional but
    a single conn.commit() at the end makes it LOOK like they are: if any
    row in the batch throws (locked file, permissions, transient I/O error),
    the whole request used to die before reaching conn.commit(), rolling
    back every DELETE in the transaction while every os.remove() that had
    already run stayed removed. That's exactly how 237 rows ended up with
    their files gone but their DB rows still present on 2026-09-11. Now a
    bad row is skipped and reported, not allowed to silently orphan every
    good row that was processed ahead of it."""
    from main import DB_PATH, DATA_DIR

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename FROM sightings WHERE review_status = 'rejected'")
    rows = cursor.fetchall()
    deleted = 0
    errors = []
    for sighting_id, filename in rows:
        try:
            image_path = os.path.join(DATA_DIR, filename)
            if os.path.exists(image_path):
                os.remove(image_path)
            cursor.execute("DELETE FROM sightings WHERE id = ?", (sighting_id,))
            conn.commit()
            deleted += 1
        except Exception as e:
            errors.append({"id": sighting_id, "filename": filename, "error": str(e)})
    conn.close()
    return {"permanently_deleted": deleted, "errors": errors}
