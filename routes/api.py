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
    """Re-run the AIY classifier on a single sighting. Updates species/confidence
    in place, stays in whatever review_status it was already in. Increments
    classification_attempts each time this is called."""
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
               common_name = ?, classification_attempts = ?
           WHERE id = ?""",
        (species_aiy, confidence_aiy, agreement, common_name, new_attempts, sighting_id)
    )
    conn.commit()
    conn.close()
    return {
        "id": sighting_id, "species_aiy": species_aiy, "confidence_aiy": confidence_aiy,
        "common_name": common_name, "classification_attempts": new_attempts
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
    it silently dropped (e.g. tagging a real squirrel as 'background')."""
    from main import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sightings SET needs_species_id = 1, species_id_status = 'queued' WHERE id = ?",
        (sighting_id,)
    )
    conn.commit()
    conn.close()
    return {"id": sighting_id, "species_id_status": "queued"}


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
    of which endpoint actually approved a given photo."""
    from datetime import datetime
    from main import DB_PATH

    species_confirmed = body.get("species_confirmed")
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
           SET species_confirmed = ?, species_id_status = 'confirmed',
               review_status = 'approved', review_updated_at = ?
           WHERE id = ?""",
        (species_confirmed, datetime.now().isoformat(), sighting_id)
    )
    conn.commit()
    conn.close()
    return {
        "id": sighting_id, "species_confirmed": species_confirmed,
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
    agreement = compute_agreement(species_aiy, confidence_aiy, species_inat, confidence_inat, is_species_level_inat)

    cursor.execute(
        """UPDATE sightings
           SET species_inat = ?, confidence_inat = ?, classifier_agreement = ?,
               species_id_status = 'classified'
           WHERE id = ?""",
        (species_inat, confidence_inat, agreement, sighting_id)
    )
    conn.commit()
    conn.close()
    return {
        "id": sighting_id, "species_inat": species_inat, "confidence_inat": confidence_inat,
        "classifier_agreement": agreement
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
