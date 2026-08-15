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
    in place, stays in whatever review_status it was already in."""
    from main import DB_PATH, DATA_DIR, classify_aiy, compute_agreement

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM sightings WHERE id = ?", (sighting_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return {"error": "Sighting not found"}

    filename = result[0]
    image_path = os.path.join(DATA_DIR, filename)
    species_aiy, confidence_aiy = classify_aiy(image_path)
    agreement = compute_agreement(species_aiy, confidence_aiy, None, None)

    cursor.execute(
        "UPDATE sightings SET species_aiy = ?, confidence_aiy = ?, classifier_agreement = ? WHERE id = ?",
        (species_aiy, confidence_aiy, agreement, sighting_id)
    )
    conn.commit()
    conn.close()
    return {"id": sighting_id, "species_aiy": species_aiy, "confidence_aiy": confidence_aiy}


@router.post("/api/trash-review/empty")
async def empty_review_trash():
    """Permanently delete review_status='rejected' sightings + their image files.
    Separate from the legacy /api/trash/empty (which uses is_trashed) so the
    old endpoint stays untouched while this one drives the new workflow."""
    from main import DB_PATH, DATA_DIR

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename FROM sightings WHERE review_status = 'rejected'")
    rows = cursor.fetchall()
    deleted = 0
    for sighting_id, filename in rows:
        image_path = os.path.join(DATA_DIR, filename)
        if os.path.exists(image_path):
            os.remove(image_path)
        cursor.execute("DELETE FROM sightings WHERE id = ?", (sighting_id,))
        deleted += 1
    conn.commit()
    conn.close()
    return {"permanently_deleted": deleted}
