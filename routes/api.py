import os
import sqlite3
from datetime import datetime
from fastapi import APIRouter

router = APIRouter()


@router.patch("/api/sightings/{sighting_id}/review-status")
async def update_review_status(sighting_id: int, body: dict):
    """Update review_status: 'pending_review', 'approved', or 'rejected'.
    Also stamps review_updated_at so trash/gallery can sort by 'most
    recently changed' - critical for finding a just-made mistake fast."""
    from main import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sightings SET review_status = ?, review_updated_at = ? WHERE id = ?",
        (body.get("review_status"), datetime.now().isoformat(), sighting_id)
    )
    conn.commit()
    conn.close()
    return {"updated": True, "id": sighting_id, "review_status": body.get("review_status")}


@router.post("/api/sightings/{sighting_id}/resend-classifier")
async def resend_classifier(sighting_id: int):
    """Re-run the AIY classifier on a single sighting, AND send it back to
    Manage's initial-screening state - review_status='pending_review',
    species_id_status='not_queued', needs_species_id=0 - regardless of what
    state it was in before. This is deliberate: resending IS how a sighting
    gets back to Manage, from anywhere in the pipeline (Manage itself,
    Species Queue, or Gallery), rather than a separate "send back" action.
    For a sighting already in Manage (already pending_review/not_queued,
    which is everything Manage shows now that it filters on
    species_id_status - see routes/manage.py) this reset is a no-op on
    those three fields; calling it from Species Queue or Gallery is what
    actually changes them. Increments classification_attempts each time
    this is called, from any page."""
    from main import DB_PATH, DATA_DIR, classify_aiy, compute_agreement, common_names

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
               common_name = ?, classification_attempts = ?,
               review_status = 'pending_review', species_id_status = 'not_queued',
               needs_species_id = 0
           WHERE id = ?""",
        (species_aiy, confidence_aiy, agreement, common_name, new_attempts, sighting_id)
    )
    conn.commit()
    conn.close()
    return {
        "id": sighting_id, "species_aiy": species_aiy, "confidence_aiy": confidence_aiy,
        "common_name": common_name, "classification_attempts": new_attempts,
        "review_status": "pending_review", "species_id_status": "not_queued"
    }


@router.post("/api/sightings/{sighting_id}/queue-species-id")
async def queue_species_id(sighting_id: int):
    """Send a sighting to the species-ID queue. This is Manage's replacement
    for the old 'Accept to Gallery' action under the revised flow: Manage
    cleanses the incoming feed (keep/reject junk), but 'keep' no longer means
    straight to Gallery - it means 'worth a species ID'. The actual Gallery
    entry point is now /confirm-species on the Species Queue page, which
    sets review_status='approved' itself once a human has picked a winner.

    Most photos are already auto-queued by the gating logic in
    classify_and_save() before a human ever sees them in Manage - this
    endpoint's real value is overriding AIY's own gating call on something
    it silently dropped (e.g. tagging a real squirrel as 'background').

    Idempotent, but only against a genuine mid-flight state. Only 'queued'
    is skipped - a sighting still on its first pass through the pipeline
    (auto-queued, waiting on SpeciesNet) shouldn't get silently reset just
    because this endpoint got called again, which is what caused duplicate
    SpeciesNet runs on 2026-09-11. 'classified' and 'confirmed' are both
    deliberately NOT skipped, for the same underlying reason even though
    they were fixed on different dates: both are completed states, not
    mid-flight ones, and a human calling this endpoint again on a completed
    sighting is asking for a legitimate re-run, not accidentally repeating
    a first pass. 'confirmed' was fixed 2026-09-12 after an earlier version
    treated it as terminal and silently broke Gallery's "send back to
    review" workflow. 'classified' had the identical bug until 2026-09-20:
    discovered when a photo's official SpeciesNet result had rolled up to
    a coarse label, its own raw classifier output actually had the right
    species, and there was no way to ask for a fresh pass after fixing the
    crop box - the endpoint just silently no-opped, because 'classified'
    was (wrongly) grouped with 'queued' as if still in progress."""
    from main import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT species_id_status FROM sightings WHERE id = ?", (sighting_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Sighting not found"}
    current_status = row[0]
    if current_status == "queued":
        conn.close()
        return {"id": sighting_id, "species_id_status": current_status, "already_in_pipeline": True}

    cursor.execute(
        "UPDATE sightings SET needs_species_id = 1, species_id_status = 'queued' WHERE id = ?",
        (sighting_id,)
    )
    conn.commit()
    conn.close()
    return {"id": sighting_id, "species_id_status": "queued", "already_in_pipeline": False}


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
    if not species_confirmed:
        return {"error": "species_confirmed is required"}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sightings WHERE id = ?", (sighting_id,))
    if not cursor.fetchone():
        conn.close()
        return {"error": "Sighting not found"}

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
