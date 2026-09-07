from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()


@router.get("/species-queue")
async def species_queue_page():
    """Read-only admin view of sightings AIY flagged as plausible birds
    (needs_species_id=1, species_id_status='queued'). Nothing acts on this
    queue yet - no second classifier exists to consume it - this exists so
    the gating decision is visible and verifiable today, and so whichever
    classifier eventually gets built (SpeciesNet or otherwise) has a real,
    already-populated backlog to work through instead of starting cold."""
    import sqlite3
    from main import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, timestamp, species_aiy, confidence_aiy, common_name "
        "FROM sightings WHERE species_id_status = 'queued' "
        "ORDER BY timestamp DESC LIMIT 200"
    )
    rows = cursor.fetchall()
    conn.close()

    cards = ""
    for r in rows:
        common = r["common_name"] or r["species_aiy"] or "Unknown"
        conf = f"{r['confidence_aiy']*100:.0f}%" if r["confidence_aiy"] is not None else ""
        cards += f"""
            <div class="q-item">
                <img src="/images/{r['filename']}">
                <div class="q-label">{common}<br><small>AIY: {conf} - {r['timestamp'].split('T')[0]}</small></div>
            </div>
        """

    empty_msg = '<p style="color:#999; padding:40px; text-align:center;">Queue is empty.</p>'
    body_grid = cards if rows else empty_msg
    count_label = f"{len(rows)} sighting{'s' if len(rows) != 1 else ''}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Species ID Queue</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }}
            .container {{ max-width: 1400px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }}
            h1 {{ margin-bottom: 10px; font-size: 24px; }}
            .subtitle {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
            .info {{ padding: 12px; background: #fff3cd; border-left: 4px solid #ffc107; margin-bottom: 20px; font-size: 13px; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px; }}
            .q-item {{ border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            .q-item img {{ width: 100%; height: 160px; object-fit: cover; display: block; }}
            .q-label {{ padding: 8px; font-size: 12px; background: #fafafa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Species ID Queue</h1>
            {NAV_HTML}
            <div class="subtitle">{count_label} flagged by AIY as plausible birds, waiting for a second-opinion classifier.</div>
            <div class="info">This queue is populated automatically by the gating logic in classify_and_save() - nothing consumes it yet. Once a second classifier (SpeciesNet or otherwise) is built, it will read from here instead of reprocessing every historical photo from scratch.</div>
            <div class="grid">
                {body_grid}
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)
