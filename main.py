import os
import secrets
import sqlite3
import logging
import csv
import numpy as np
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, Query, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, FileResponse
from migration import migrate_v1_to_v2, migrate_v2_to_v3, migrate_v3_to_v4
from PIL import Image
import tflite_runtime.interpreter as tflite
from routes.nav import NAV_HTML

app = FastAPI()

# --- Admin auth (HTTP Basic) ---
# Protects Manage/Gallery/Trash/Stats/the legacy dashboard, and full-resolution
# image access. Does NOT protect /webhook (the camera has no way to send
# credentials) or the new /public routes (family access is meant to be
# link-only, no login). Credentials come from the environment - see
# docker-compose.yml - with a default that is intentionally obviously insecure
# so it's impossible to mistake for a real deployment value. If Funnel is
# enabled while these defaults are still in place, that is a real, live
# exposure - not a hypothetical one.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME") or "changeme"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "changeme"
_security = HTTPBasic()


def verify_admin_auth(credentials: HTTPBasicCredentials = Depends(_security)):
    # secrets.compare_digest avoids a timing side-channel that a naive ==
    # comparison would have - not a huge deal for a single-family app, but
    # it's free correctness once you know to use it.
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return credentials.username

DATA_DIR = "/app/data/images"
DB_PATH = "/app/data/birds.db"
MODEL_DIR = "/app/models"
AIY_MODEL_PATH = os.path.join(MODEL_DIR, "aiy_birds_v1.tflite")
AIY_LABELS_PATH = os.path.join(MODEL_DIR, "aiy_birds_labelmap.csv")

# Birdbath crop box (left, top, right, bottom) in the original 1920x1080 frame.
# Determined by visually checking candidate boxes against real capture photos
# (not just the motion-detection ROI, which is intentionally more generous).
# This box was verified to fully contain both the bath rim/bowl AND a bird
# perched at the left rim edge - a real position confirmed from an actual photo,
# not just a symmetric guess. Cropping here before the classifier resizes down
# to its small input size preserves far more pixel detail on the bird itself,
# instead of spending that detail on driveway/street in the background.
CROP_BOX = (500, 400, 1300, 900)

# Public-display crop box (left, top, right, bottom) in the original 1920x1080
# frame. Deliberately a separate named constant from CROP_BOX above, even
# though the value is currently identical - CROP_BOX exists to feed the
# classifier and could change for accuracy reasons; this one exists to hide
# house/garage/driveway/street from the public family page and could need to
# change for privacy reasons even if CROP_BOX never does. Never let something
# else silently reuse this constant assuming they'll always match.
#
# VERIFIED 2026-09-07 against a real photo (bird_20260907_154952.jpg, a real
# bird at the bath). Iterated using a labeled pixel grid overlaid on the real
# photo so exact numbers could be picked by eye rather than guessed: started
# at (400,400,1400,1100), clamped/refined to match the original frame's
# 16:9 aspect ratio exactly (1000x562, ratio 1.7794 vs 16:9's 1.7778) by
# trimming the bottom - the left edge didn't need to move once top and right
# were fixed at their privacy-verified values, since width was already
# correct for that ratio. Final value confirmed by inspecting the actual
# cropped output, not just the box drawn on the original: no house, garage,
# car, or street visible anywhere in it - only mulch, the birdbath itself,
# and a small intentional sliver of the brick walkway in the top-left
# corner, an explicitly accepted trade-off, not an oversight.
# If the camera is ever physically re-aimed or reinstalled, re-verify this
# the same way (grid overlay on a fresh photo, inspect the actual crop
# output) before trusting it again.
PUBLIC_DISPLAY_CROP = (400, 400, 1400, 962)

# Auto-trash on low AIY confidence: DISABLED (set to None) after testing the
# idea against the real 202-row database on 2026-09-07. Set to a float to
# re-enable; None means "never auto-trash on confidence".
#
# WHY IT'S OFF: the original plan was to auto-reject low-confidence frames as
# junk. Measured against 22 human-APPROVED photos, a 0.3 threshold would have
# auto-trashed 11 of them - real, confirmed birds including a Pileated
# Woodpecker (0.055), House Sparrow (0.094), California Scrub-Jay (0.148) and
# Northern Flicker (0.188). Sweeping the threshold showed confidence has
# almost no discriminative power on this data:
#     0.10 -> loses 14% of approved, catches 17% of rejected
#     0.15 -> loses 36% of approved, catches 33% of rejected
#     0.20 -> loses 50% of approved, catches 49% of rejected
#     0.30 -> loses 50% of approved, catches 71% of rejected
# Losing real birds at roughly the same rate it catches junk means the signal
# isn't there. AIY runs low-confidence across the board here (Cedar Waxwings
# top out at 0.199), so this isn't a tuning problem - the score just doesn't
# mean "is this a bird". Revisit only with a classifier whose confidence is
# actually calibrated for this, or with a different signal entirely.
AUTO_TRASH_CONFIDENCE_THRESHOLD = None

# Auto-trash when AIY's top label is literally "background": ALSO DISABLED.
# Seems obviously safe, but 2 of the 22 approved photos have
# species_aiy='background' (common_name "No bird detected") - so even this
# narrower rule would have discarded photos that were deliberately kept.
# Set to True to re-enable.
AUTO_TRASH_ON_BACKGROUND_LABEL = False

os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("birdapp")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            filename TEXT,
            status TEXT DEFAULT 'acquired',
            species_aiy TEXT,
            confidence_aiy REAL,
            species_inat TEXT,
            confidence_inat REAL,
            species_confirmed TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()
migrate_v1_to_v2(DB_PATH)
migrate_v2_to_v3(DB_PATH)
migrate_v3_to_v4(DB_PATH)

# --- AIY (Google) bird classifier: loads once at startup, fails soft if files are missing ---
aiy_interpreter = None
aiy_labels = {}
aiy_input_details = None
aiy_output_details = None


def load_aiy_model():
    global aiy_interpreter, aiy_labels, aiy_input_details, aiy_output_details
    try:
        aiy_interpreter = tflite.Interpreter(model_path=AIY_MODEL_PATH)
        aiy_interpreter.allocate_tensors()
        aiy_input_details = aiy_interpreter.get_input_details()
        aiy_output_details = aiy_interpreter.get_output_details()
        with open(AIY_LABELS_PATH, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                try:
                    idx = int(row[0])
                except ValueError:
                    continue  # skip a header row if the CSV has one
                aiy_labels[idx] = row[1] if len(row) > 1 else str(idx)
        logger.info(
            "AIY bird model loaded: %d labels, input shape %s, dtype %s",
            len(aiy_labels), aiy_input_details[0]['shape'], aiy_input_details[0]['dtype']
        )
    except Exception as e:
        logger.error("Failed to load AIY model (classification will be skipped): %s", e)


load_aiy_model()

# --- Scientific -> common name mapping. The AIY labelmap only ships scientific
# names (id,name) with no common-name column, so this is a separately-built
# lookup, generated once via the iNaturalist taxa API and checked into the
# repo as a static file rather than calling out to that API at runtime. ---
COMMON_NAMES_PATH = os.path.join(os.path.dirname(__file__), "common_names.csv")
common_names = {}


def load_common_names():
    global common_names
    if not os.path.exists(COMMON_NAMES_PATH):
        logger.warning("common_names.csv not found - common_name will stay blank")
        return
    with open(COMMON_NAMES_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("scientific_name") and row.get("common_name"):
                common_names[row["scientific_name"]] = row["common_name"]
    logger.info("Loaded %d scientific->common name mappings", len(common_names))


load_common_names()

def classify_aiy(image_path):
    """Run the Google AIY bird classifier. Returns (species, confidence) or (None, None) if unavailable.
    Reads the model's own input dtype at runtime instead of assuming float vs. quantized,
    so this adapts correctly whether the model turns out to be float32 or uint8 quantized."""
    if aiy_interpreter is None:
        return None, None
    try:
        _, height, width, _ = aiy_input_details[0]['shape']
        img = Image.open(image_path).convert("RGB")
        # Crop to the birdbath area before resizing, so the bird gets the
        # classifier's full input resolution instead of sharing it with the
        # driveway/street that surround it in the full wide-angle frame.
        img = img.crop(CROP_BOX)
        img = img.resize((width, height))
        arr = np.array(img)

        input_dtype = aiy_input_details[0]['dtype']
        if input_dtype == np.float32:
            input_data = np.expand_dims(arr.astype(np.float32) / 255.0, axis=0)
        else:
            input_data = np.expand_dims(arr.astype(input_dtype), axis=0)

        aiy_interpreter.set_tensor(aiy_input_details[0]['index'], input_data)
        aiy_interpreter.invoke()
        output = aiy_interpreter.get_tensor(aiy_output_details[0]['index'])[0]

        output_dtype = aiy_output_details[0]['dtype']
        if output_dtype != np.float32:
            scale, zero_point = aiy_output_details[0]['quantization']
            output = (output.astype(np.float32) - zero_point) * scale if scale else output.astype(np.float32)

        top_idx = int(np.argmax(output))
        confidence = float(output[top_idx])
        species = aiy_labels.get(top_idx, f"Unknown (class {top_idx})")
        return species, confidence
    except Exception as e:
        logger.exception("AIY classification failed: %s", e)
        return None, None


def compute_agreement(species_aiy, confidence_aiy, species_inat, confidence_inat):
    """Determine classifier_agreement state from two classifiers' output.
    Handles the case where one classifier hasn't run / isn't wired in yet -
    that's 'one_classifier', distinct from 'pending' (both still running)."""
    if species_aiy and not species_inat:
        return 'one_classifier'
    if species_inat and not species_aiy:
        return 'one_classifier'
    if not species_aiy and not species_inat:
        return 'pending'

    if species_aiy == species_inat:
        if confidence_aiy >= 0.75 and confidence_inat >= 0.75:
            return 'agreed'
        return 'low_confidence'
    return 'disagreed'


def classify_and_save(image_path, sighting_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE sightings SET status = 'identifying' WHERE id = ?", (sighting_id,))
    conn.commit()

    species_aiy, confidence_aiy = classify_aiy(image_path)
    common_name = common_names.get(species_aiy) if species_aiy else None

    # species_inat / confidence_inat intentionally left NULL for now.
    # iNaturalist small-model integration was investigated and abandoned
    # (2026-09-07): the underlying TF Hub asset is deleted, and AIY is itself
    # trained on iNaturalist data, so it would not have been a genuinely
    # independent second opinion anyway. See PROJECT_MASTER_MAP rev8.
    species_inat, confidence_inat = None, None

    agreement = compute_agreement(species_aiy, confidence_aiy, species_inat, confidence_inat)

    # --- Gating logic (2026-09-07) ---
    # AIY runs on every photo, same as always - unchanged and cheap. What's
    # new is what happens to the RESULT.
    #
    # Auto-trash is OFF by default (see the constants above - measured
    # against real data, AIY's confidence doesn't actually separate birds
    # from junk here, and turning it on would have discarded half the
    # human-approved photos). Both switches are left in place, wired and
    # ready, so re-enabling is a one-line change if a better signal shows up.
    #
    # What DOES happen unconditionally: anything AIY didn't call junk gets
    # flagged needs_species_id=1 / species_id_status='queued'. Nothing
    # consumes that queue yet - no second classifier exists - but the moment
    # one does, it has a real, already-populated backlog instead of needing
    # to reprocess the entire photo library from scratch. This part is
    # non-destructive, which is why it's safe to run by default while the
    # auto-trash half stays off.
    is_background_or_junk = (
        species_aiy is None
        or (AUTO_TRASH_ON_BACKGROUND_LABEL and species_aiy == "background")
        or (
            AUTO_TRASH_CONFIDENCE_THRESHOLD is not None
            and confidence_aiy is not None
            and confidence_aiy < AUTO_TRASH_CONFIDENCE_THRESHOLD
        )
    )

    if is_background_or_junk:
        review_status = "rejected"
        needs_species_id = 0
        species_id_status = "not_queued"
        auto_note = "auto-rejected: background or confidence below threshold"
    else:
        review_status = "pending_review"
        needs_species_id = 1
        species_id_status = "queued"
        auto_note = None

    cursor.execute(
        """UPDATE sightings
           SET status = 'identified', species_aiy = ?, confidence_aiy = ?,
               species_inat = ?, confidence_inat = ?, classifier_agreement = ?,
               common_name = ?, review_status = ?, review_updated_at = ?,
               needs_species_id = ?, species_id_status = ?,
               notes = COALESCE(notes, ?)
           WHERE id = ?""",
        (species_aiy, confidence_aiy, species_inat, confidence_inat, agreement,
         common_name, review_status, datetime.now().isoformat(),
         needs_species_id, species_id_status, auto_note, sighting_id)
    )
    conn.commit()
    conn.close()


@app.post("/webhook")
async def motion_webhook(background_tasks: BackgroundTasks, image: UploadFile = File(...), message: str = Form(None)):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bird_{timestamp}.jpg"
    image_path = os.path.join(DATA_DIR, filename)

    try:
        contents = await image.read()
        with open(image_path, "wb") as f:
            f.write(contents)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sightings (timestamp, filename, status) VALUES (?, ?, 'acquired')",
            (datetime.now().isoformat(), filename)
        )
        sighting_id = cursor.lastrowid
        conn.commit()
        conn.close()

        background_tasks.add_task(classify_and_save, image_path, sighting_id)
        return {"status": "success", "file": filename, "id": sighting_id}
    except Exception as e:
        logger.exception("webhook error")
        return {"status": "error", "message": str(e)}


@app.get("/images/{filename}")
async def get_full_image(filename: str, username: str = Depends(verify_admin_auth)):
    """Full-resolution, uncropped original - admin/reviewer use only.
    This used to be a bare StaticFiles mount with NO auth at all, which meant
    every original photo (house, garage, driveway, everything) was reachable
    by anyone who could guess a filename - and bird_YYYYMMDD_HHMMSS.jpg
    timestamps are trivially guessable/enumerable. That was already a real
    gap on the Tailscale-only network; it would have been a much bigger one
    the moment Funnel exposed this port to the whole internet. Replacing the
    mount with an explicit route is what makes auth enforcement possible here
    at all - a plain StaticFiles mount can't carry a Depends(). The public
    family page must NEVER call this route - it has its own separate,
    cropped, gated image endpoint in routes/public.py instead."""
    # Reject path traversal / anything that isn't a bare filename before ever
    # touching the filesystem - filename comes straight from the URL.
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    image_path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(image_path)


@app.get("/", response_class=HTMLResponse)
async def dashboard(username: str = Depends(verify_admin_auth)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, filename, status, species_aiy, confidence_aiy, species_confirmed "
        "FROM sightings ORDER BY id DESC LIMIT 20"
    )
    rows = cursor.fetchall()
    conn.close()

    html = """
    <html>
        <head>
            <title>Birdbath AI Classifier</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; background: #f4f4f9; color: #333; }
                h1 { color: #2c3e50; }
                .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; }
                .card { background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                img { width: 100%; height: 160px; object-fit: cover; border-radius: 4px; }
                .status { font-size: 0.8em; color: #888; }
            </style>
        </head>
        <body>
            <h1>🐦 Birdbath Visitor Dashboard</h1>
            __NAV__
            <div class="grid">
    """
    for row in rows:
        ts, fn, status, species_aiy, confidence_aiy, species_confirmed = row
        display_species = species_confirmed or species_aiy or "Unidentified"
        conf_str = f"{confidence_aiy:.0%}" if confidence_aiy is not None else ""
        html += f"""
            <div class="card">
                <img src="/images/{fn}" />
                <h3>{display_species}</h3>
                <p><small>{ts}</small></p>
                <p class="status">status: {status} {conf_str}</p>
            </div>
        """
    html += """
            </div>
        </body>
    </html>
    """
    html = html.replace("__NAV__", NAV_HTML)
    return html


def _build_filter_where(f: dict):
    """Shared WHERE-clause builder for filter/delete/retag - keeps filter
    semantics identical across all three endpoints."""
    where_parts = ["is_trashed = 0"]
    params = []
    if f.get("species"):
        where_parts.append("(species_confirmed = ? OR (species_confirmed IS NULL AND species_aiy = ?))")
        params.extend([f["species"], f["species"]])
    if f.get("confidence_min") is not None or f.get("confidence_max") is not None:
        where_parts.append("confidence_aiy BETWEEN ? AND ?")
        params.extend([f.get("confidence_min", 0.0), f.get("confidence_max", 1.0)])
    if f.get("inbox_status"):
        where_parts.append("inbox_status = ?")
        params.append(f["inbox_status"])
    if f.get("date_from"):
        where_parts.append("timestamp >= ?")
        params.append(f["date_from"] + "T00:00:00")
    if f.get("date_to"):
        where_parts.append("timestamp <= ?")
        params.append(f["date_to"] + "T23:59:59")
    return " AND ".join(where_parts), params


@app.get("/api/sightings")
async def list_sightings(
    confidence_min: float = Query(0.0, ge=0, le=1),
    confidence_max: float = Query(1.0, ge=0, le=1),
    species: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    inbox_status: str = Query(None),
    review_status: str = Query(None),
    is_trashed: bool = Query(False),
    sort_by: str = Query("timestamp"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    username: str = Depends(verify_admin_auth),
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # review_status is the primary filter for the new manage/gallery/trash workflow.
    # When provided, it replaces the legacy is_trashed filter entirely - a
    # 'rejected' review_status IS what trash means now, so filtering by both
    # would be redundant and could conflict for older rows.
    if review_status:
        where_parts = ["review_status = ?"]
        params = [review_status]
    else:
        where_parts = ["is_trashed = ?"]
        params = [1 if is_trashed else 0]

    if species:
        where_parts.append("(species_confirmed = ? OR (species_confirmed IS NULL AND species_aiy = ?))")
        params.extend([species, species])
    if confidence_min > 0 or confidence_max < 1:
        where_parts.append("confidence_aiy BETWEEN ? AND ?")
        params.extend([confidence_min, confidence_max])
    if inbox_status:
        where_parts.append("inbox_status = ?")
        params.append(inbox_status)
    if date_from:
        where_parts.append("timestamp >= ?")
        params.append(date_from + "T00:00:00")
    if date_to:
        where_parts.append("timestamp <= ?")
        params.append(date_to + "T23:59:59")

    where_clause = " AND ".join(where_parts)

    cursor.execute(f"SELECT COUNT(*) FROM sightings WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    # Whitelist sort_by against actual column names - it gets string-interpolated
    # into the query below, so this isn't optional even though it's a GET param.
    sort_column = "review_updated_at" if sort_by == "review_updated_at" else "timestamp"

    offset = (page - 1) * limit
    cursor.execute(
        f"""SELECT * FROM sightings WHERE {where_clause}
           ORDER BY is_favorite DESC, {sort_column} DESC
           LIMIT ? OFFSET ?""",
        params + [limit, offset]
    )
    rows = cursor.fetchall()
    conn.close()
    return {"total": total, "page": page, "limit": limit, "items": [dict(r) for r in rows]}


@app.post("/api/sightings/delete-filtered")
async def delete_filtered(filters: dict, username: str = Depends(verify_admin_auth)):
    """Move matching sightings to trash (is_trashed=1). Reversible - files
    are untouched. Permanent removal only happens via /api/trash/empty."""
    where_clause, params = _build_filter_where(filters)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE sightings SET is_trashed = 1 WHERE {where_clause}", params)
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return {"trashed": count}


@app.post("/api/sightings/retag")
async def retag_filtered(payload: dict, username: str = Depends(verify_admin_auth)):
    """Body: {"filters": {...}, "new_species": "..."}. Sets species_confirmed
    on every sighting matching the filters."""
    filters = payload.get("filters", {})
    new_species = payload.get("new_species")
    if not new_species:
        return {"error": "new_species is required"}
    where_clause, params = _build_filter_where(filters)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE sightings SET species_confirmed = ? WHERE {where_clause}",
        [new_species] + params
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return {"retagged": count}


@app.post("/api/trash/empty")
async def empty_trash(username: str = Depends(verify_admin_auth)):
    """Permanently delete trashed sightings AND their image files. Not reversible."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename FROM sightings WHERE is_trashed = 1")
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


@app.get("/api/stats")
async def stats(username: str = Depends(verify_admin_auth)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM sightings WHERE is_trashed=0")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sightings WHERE is_trashed=0 AND confidence_aiy < 0.5")
    low_conf = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sightings WHERE is_trashed=1")
    trashed = cursor.fetchone()[0]

    cursor.execute("""
        SELECT species_aiy, COUNT(*) as count
        FROM sightings
        WHERE is_trashed=0 AND confidence_aiy > 0.5
        GROUP BY species_aiy
        ORDER BY count DESC
        LIMIT 5
    """)
    top_species = [{"species": r[0], "count": r[1]} for r in cursor.fetchall()]

    conn.close()
    return {
        "total_sightings": total,
        "low_confidence_count": low_conf,
        "trashed_count": trashed,
        "top_species": top_species
    }


@app.get("/api/species-list")
async def species_list(username: str = Depends(verify_admin_auth)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT species_confirmed FROM sightings
        WHERE is_trashed=0 AND species_confirmed IS NOT NULL
        UNION
        SELECT DISTINCT species_aiy FROM sightings
        WHERE is_trashed=0 AND species_aiy IS NOT NULL AND species_aiy != 'background'
        ORDER BY 1
    """)
    species = [row[0] for row in cursor.fetchall()]
    conn.close()
    # value = the actual DB value filters compare against (scientific name, or
    # a manually-confirmed name); label = common name where we have one,
    # falling back to the raw value so custom/unmapped entries still display.
    return {"species": [{"value": s, "label": common_names.get(s, s)} for s in species]}


# New modular routes: manage (review), gallery (approved), trash (rejected),
# and their supporting API endpoints. Imported at the bottom, after DB_PATH,
# DATA_DIR, classify_aiy, and compute_agreement are all defined above, since
# routes/api.py imports those from this module at call-time.
from routes.manage import router as manage_router
from routes.gallery import router as gallery_router
from routes.trash import router as trash_router
from routes.api import router as review_api_router
from routes.species_queue import router as species_queue_router
from routes.public import router as public_router

# Every existing admin router gets the SAME auth dependency applied at the
# include_router() level - this protects every route already defined inside
# each of these files without having to touch their individual @router.get/
# post decorators one by one. species_queue is new but is an admin-only view
# (it shows AIY's raw internal gating decisions), so it gets the same
# treatment. public is the one deliberate exception - no dependency at all,
# by design, since family access is meant to be link-only with no login.
_admin_deps = [Depends(verify_admin_auth)]
app.include_router(manage_router, dependencies=_admin_deps)
app.include_router(gallery_router, dependencies=_admin_deps)
app.include_router(trash_router, dependencies=_admin_deps)
app.include_router(review_api_router, dependencies=_admin_deps)
app.include_router(species_queue_router, dependencies=_admin_deps)
app.include_router(public_router)
