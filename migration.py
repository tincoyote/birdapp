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


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/birds.db"
    migrate_v1_to_v2(path)
    print(f"Migration complete: {path}")
