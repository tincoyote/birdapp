import os
import io
import sqlite3
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from PIL import Image

router = APIRouter()


def _get_db_path():
    from main import DB_PATH
    return DB_PATH


def _get_data_dir():
    from main import DATA_DIR
    return DATA_DIR


def _get_crop_box():
    from main import PUBLIC_DISPLAY_CROP
    return PUBLIC_DISPLAY_CROP


@router.get("/api/public/sightings")
async def public_sightings():
    """Read-only, unauthenticated. Hardcoded to review_status='approved' -
    does NOT accept any client-supplied status/filter override, unlike the
    admin /api/sightings endpoint. This is the ONLY data path the public
    page is allowed to use."""
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, timestamp, species_aiy, common_name "
        "FROM sightings WHERE review_status = 'approved' "
        "ORDER BY timestamp DESC LIMIT 100"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    # Deliberately thin payload: no confidence score, no notes, no review
    # metadata - family doesn't need that detail, and it's one less thing
    # that could ever leak.
    return {"items": [
        {"id": r["id"], "filename": r["filename"], "timestamp": r["timestamp"],
         "label": r["common_name"] or r["species_aiy"] or "Unknown bird"}
        for r in rows
    ]}


@router.get("/public-images/{filename}")
async def public_image(filename: str):
    """Privacy-cropped image, and ONLY for sightings that are actually
    review_status='approved' - checked fresh against the DB on every
    request, not trusted from the filename alone. Someone directly guessing
    or enumerating a filename that ISN'T approved (pending/rejected) gets a
    404, never the image - this is what makes the crop a real guarantee
    instead of just "we remembered to crop it when building the page."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM sightings WHERE filename = ? AND review_status = 'approved'",
        (filename,)
    )
    is_approved = cursor.fetchone() is not None
    conn.close()
    if not is_approved:
        raise HTTPException(status_code=404, detail="Not found")

    image_path = os.path.join(_get_data_dir(), filename)
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Not found")

    img = Image.open(image_path).convert("RGB")
    img = img.crop(_get_crop_box())
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


@router.get("/family")
async def family_page():
    """Public, unauthenticated, read-only. No admin nav, no mutate actions,
    no links to Manage/Gallery/Trash/Stats - a stranger with this URL (once
    Funnel is on) should see nothing but a simple photo gallery, no hint the
    admin workflow even exists."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Birdbath Visitors</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            h1 { text-align: center; margin-bottom: 6px; color: #2c3e50; }
            .subtitle { text-align: center; color: #888; margin-bottom: 24px; font-size: 14px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
            .card { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
            .card img { width: 100%; height: 200px; object-fit: cover; display: block; }
            .card-label { padding: 10px 12px; font-size: 14px; }
            .card-label small { color: #999; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🐦 Birdbath Visitors</h1>
            <div class="subtitle">Recent guests at the backyard birdbath</div>
            <div class="grid" id="grid"><p style="text-align:center; color:#999;">Loading...</p></div>
        </div>
        <script>
            async function load() {
                const res = await fetch('/api/public/sightings');
                const data = await res.json();
                const grid = document.getElementById('grid');
                grid.innerHTML = '';
                if (data.items.length === 0) {
                    grid.innerHTML = '<p style="text-align:center; color:#999; grid-column:1/-1;">No visitors yet - check back soon!</p>';
                    return;
                }
                data.items.forEach(s => {
                    const date = s.timestamp.split('T')[0];
                    grid.insertAdjacentHTML('beforeend', `
                        <div class="card">
                            <img src="/public-images/${s.filename}" loading="lazy">
                            <div class="card-label">${s.label}<br><small>${date}</small></div>
                        </div>
                    `);
                });
            }
            load();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
