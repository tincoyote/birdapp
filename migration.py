"""
BLOCK 4.1 schema migration: adds bulk-management columns to the sightings table.
Idempotent - checks for each column's existence before adding, so it's safe
to call on every container startup without special-casing "first run".
"""
import sqlite3


def migrate_v1_to_v2(db_path):
    """Add BLOCK 4 columns to sightings table if they don't already exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(sightings)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "is_trashed" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN is_trashed INTEGER DEFAULT 0")
    if "is_favorite" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN is_favorite INTEGER DEFAULT 0")
    if "inbox_status" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN inbox_status TEXT DEFAULT 'new'")
    if "classifier_agreement" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN classifier_agreement TEXT DEFAULT 'pending'")
    if "review_status" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN review_status TEXT DEFAULT 'pending_review'")
    if "review_updated_at" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN review_updated_at TEXT")

    # Backfill review_updated_at so trash/gallery sort-by-recent-change has
    # something to work with for pre-existing rows, instead of NULLs sorting
    # unpredictably. Falls back to the original sighting timestamp.
    cursor.execute("""
        UPDATE sightings SET review_updated_at = timestamp
        WHERE review_updated_at IS NULL
    """)

    # Backfill: rows that predate this migration already have an AIY result
    # and no iNat result (iNat isn't wired in yet). That's the 'one_classifier'
    # state, not 'pending' - pending implies a classifier is still running.
    cursor.execute("""
        UPDATE sightings SET classifier_agreement = 'one_classifier'
        WHERE species_aiy IS NOT NULL AND species_inat IS NULL
          AND classifier_agreement = 'pending'
    """)

    # Same backfill logic for inbox_status: pre-existing identified sightings
    # never went through a review step, so treat them as already reviewed
    # rather than flooding a brand-new inbox with 252 historical rows.
    cursor.execute("""
        UPDATE sightings SET inbox_status = 'posted'
        WHERE inbox_status = 'new' AND status = 'identified'
    """)

    conn.commit()
    conn.close()


def migrate_v2_to_v3(db_path):
    """Add common_name, classification_attempts, and notes columns.
    Same idempotent PRAGMA table_info pattern as migrate_v1_to_v2."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(sightings)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "common_name" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN common_name TEXT")
    if "classification_attempts" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN classification_attempts INTEGER DEFAULT 1")
    if "notes" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN notes TEXT")

    # Backfill: every pre-existing row that already has a species_aiy result
    # was classified exactly once (classification_attempts wasn't tracked
    # yet), so 1 is the correct historical value, not a guess.
    cursor.execute("""
        UPDATE sightings SET classification_attempts = 1
        WHERE species_aiy IS NOT NULL AND classification_attempts IS NULL
    """)

    conn.commit()
    conn.close()


def migrate_v3_to_v4(db_path):
    """Add species-ID queue scaffolding: needs_species_id / species_id_status.
    Deliberately a SEPARATE column pair from review_status, not a new
    review_status value - the human approve/reject workflow (Manage/Gallery/
    Trash) and "does this need a second-opinion classifier eventually" are
    independent questions. A sighting can be approved to Gallery by a human
    today and still sit in the species-ID queue waiting for a second
    classifier that doesn't exist yet - decoupling these means building the
    queue now doesn't touch or risk the working review workflow at all.
    Same idempotent PRAGMA table_info pattern as prior migrations.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(sightings)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "needs_species_id" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN needs_species_id INTEGER DEFAULT 0")
    if "species_id_status" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN species_id_status TEXT DEFAULT 'not_queued'")

    conn.commit()
    conn.close()


def migrate_v4_to_v5(db_path):
    """Add species_confirmed_source: tracks whether a confirmed species came
    from clicking 'Post as AIY' ('aiy'), 'Post as SpeciesNet' ('sn'), or a
    manually-typed override ('custom'). species_confirmed itself doesn't
    distinguish these - a button pick and a hand-typed correction look
    identical once saved - so there was no way to tell them apart after the
    fact. NULL for pre-existing confirmed rows since the real source was
    never recorded and shouldn't be guessed at retroactively.
    Same idempotent PRAGMA table_info pattern as prior migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(sightings)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "species_confirmed_source" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN species_confirmed_source TEXT")

    conn.commit()
    conn.close()


def migrate_v5_to_v6(db_path):
    """Add species_inat_raw_guess / confidence_inat_raw: SpeciesNet's top
    pre-rollup classifier candidate and score, captured even when the
    ensemble's own confidence-margin logic rolled the official prediction
    up to a coarser label (e.g. 'bird'). Discovered 2026-09-20 that a rolled-
    up result can still have the correct species sitting in the raw
    classifier output - e.g. official prediction 'bird' at a rollup-adjusted
    0.944, while the raw top candidate was 'California Scrub-Jay' at 0.52,
    matching AIY's own independent guess for the same photo. Previously
    that raw candidate was computed by run_second_opinion.py and then
    silently discarded - these columns keep it instead of throwing it away.
    NULL for every pre-existing row and for any row where SpeciesNet
    resolved to species level directly (nothing rolled up, so there's no
    separate 'raw' guess worth keeping - species_inat already has it).
    Same idempotent PRAGMA table_info pattern as prior migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(sightings)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "species_inat_raw_guess" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN species_inat_raw_guess TEXT")
    if "confidence_inat_raw" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN confidence_inat_raw REAL")

    conn.commit()
    conn.close()


def migrate_v6_to_v7(db_path):
    """MegaDetector + per-bird AIY (2026-10-20, docs/PLAN-detector.md).

    New `detections` table: one row per animal/person/vehicle MegaDetector
    finds in a photo, so a photo can hold several birds of different
    species. bbox is normalized (0-1) x, y, w, h of the full frame.
    species_confirmed/_source are the per-bird human name, same format as
    sightings.species_confirmed ("Common (Latin)" or a custom string).

    New sightings columns summarise the detections for Manage's filters:
    detect_status ('pending' -> 'done'/'failed'), animal_count,
    person_count, max_det_conf (best animal detection, 0 if none),
    detector_model, detected_at.

    A trigger removes a sighting's detections when the sighting row is
    deleted, so every existing delete path (both trash-empty endpoints)
    stays correct without being edited.

    One-time backfill: when the detect_status column is first added, every
    existing sighting is marked 'pending', so the worker re-runs the
    current photos automatically after deploy (newest first). Guarded by
    the column check, so it never re-queues anything on later restarts."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sighting_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            category TEXT NOT NULL,
            det_conf REAL NOT NULL,
            x REAL, y REAL, w REAL, h REAL,
            species_aiy TEXT,
            confidence_aiy REAL,
            common_name TEXT,
            species_confirmed TEXT,
            species_confirmed_source TEXT,
            created_at TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_sighting ON detections(sighting_id)")
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_sightings_delete_detections
        AFTER DELETE ON sightings
        BEGIN
            DELETE FROM detections WHERE sighting_id = OLD.id;
        END
    """)

    cursor.execute("PRAGMA table_info(sightings)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    first_time = "detect_status" not in existing_cols
    if first_time:
        cursor.execute("ALTER TABLE sightings ADD COLUMN detect_status TEXT DEFAULT 'pending'")
    if "animal_count" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN animal_count INTEGER")
    if "person_count" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN person_count INTEGER")
    if "max_det_conf" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN max_det_conf REAL")
    if "detector_model" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN detector_model TEXT")
    if "detected_at" not in existing_cols:
        cursor.execute("ALTER TABLE sightings ADD COLUMN detected_at TEXT")
    if first_time:
        cursor.execute("UPDATE sightings SET detect_status = 'pending'")
        # SpeciesNet wrote cats as bare 'Felis catus'; Species Queue's Cat
        # button writes 'Domestic Cat (Felis catus)'. One name, one group.
        cursor.execute("UPDATE sightings SET species_confirmed = 'Domestic Cat (Felis catus)' "
                       "WHERE species_confirmed = 'Felis catus'")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sightings_detect_status ON sightings(detect_status)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/birds.db"
    migrate_v1_to_v2(path)
    migrate_v2_to_v3(path)
    migrate_v3_to_v4(path)
    migrate_v4_to_v5(path)
    migrate_v5_to_v6(path)
    migrate_v6_to_v7(path)
    print(f"Migration complete: {path}")
