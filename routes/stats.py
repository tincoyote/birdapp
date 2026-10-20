import html as html_module
import sqlite3
from urllib.parse import quote
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()

SOURCE_LABELS = {"aiy": "AIY", "sn": "SpeciesNet (retired 2026-10-20)", "custom": "Typed by you"}

PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Stats</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1100px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
        h1 { font-size: 24px; margin-bottom: 10px; }
        h2 { font-size: 17px; margin: 26px 0 10px; }
        .cards { display: flex; flex-wrap: wrap; gap: 12px; }
        .card { flex: 1; min-width: 150px; background: #f8f9fa; border-radius: 6px; padding: 14px; text-decoration: none; color: inherit; }
        .card:hover { background: #e9ecef; }
        .card .n { font-size: 28px; font-weight: 700; }
        .card .l { font-size: 12px; color: #666; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { text-align: left; font-size: 12px; color: #666; border-bottom: 2px solid #dee2e6; padding: 6px 8px; }
        td { border-bottom: 1px solid #eee; padding: 6px 8px; }
        td.num, th.num { text-align: right; }
        .latin { color: #888; font-style: italic; font-size: 12px; }
        a { color: #007bff; }
        .empty { color: #999; padding: 12px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Stats</h1>
        __NAV__
        <h2>Where photos are right now</h2>
        <div class="cards">__PIPELINE__</div>
        <h2>Bird detector</h2>
        __DETECTOR__
        <h2>Gallery by species</h2>
        __SPECIES__
        <h2>Who named the Gallery photos</h2>
        __SOURCES__
        <h2>Last 14 days</h2>
        __DAILY__
    </div>
</body>
</html>
"""


def _e(s):
    return html_module.escape(str(s))


@router.get("/stats")
async def stats_page():
    """Admin stats (2026-09-26). Replaces the old /api/stats JSON, which
    counted AIY's first guesses via the legacy is_trashed flag. Everything
    here uses the same 'effective species' rule as the Gallery filter:
    the confirmed name if a human picked one, else AIY's guess - so each
    species link opens exactly the photos that were counted."""
    from main import DB_PATH, common_names

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    one = lambda sql: c.execute(sql).fetchone()[0]

    pipeline = [
        ("/manage", one("SELECT COUNT(*) FROM sightings WHERE review_status='pending_review' AND species_id_status='not_queued'"), "In Manage"),
        ("/species-queue", one("SELECT COUNT(*) FROM sightings WHERE species_id_status='queued' AND review_status!='rejected'"), "Being scanned for birds"),
        ("/species-queue", one("SELECT COUNT(*) FROM sightings WHERE species_id_status='classified' AND review_status!='rejected'"), "Ready in Species Queue"),
        ("/gallery", one("SELECT COUNT(*) FROM sightings WHERE review_status='approved'"), "In Gallery"),
        ("/trash", one("SELECT COUNT(*) FROM sightings WHERE review_status='rejected'"), "In Trash"),
    ]
    pipeline_html = "".join(
        f'<a class="card" href="{href}"><div class="n">{n}</div><div class="l">{_e(label)}</div></a>'
        for href, n, label in pipeline
    )

    # --- detector status (live state from the worker thread + DB counts) ---
    import detector
    from main import DETECTOR_CONFIG
    st = detector.state
    waiting = one("SELECT COUNT(*) FROM sightings WHERE detect_status='pending'")
    failed = one("SELECT COUNT(*) FROM sightings WHERE detect_status='failed'")
    multi = one("SELECT COUNT(*) FROM sightings WHERE detect_status='done' AND animal_count >= 2")
    if not st["enabled"]:
        status = "Off (detector.enabled is false in camera_config.json)"
    elif st["loaded"]:
        status = f"Running - {st['model']}"
    else:
        status = "Not running" + (f" - {st['error']}" if st.get("error") else " (starting up)")
    avg = f"{st['avg_seconds']:.1f} s" if st.get("avg_seconds") else "-"
    backlog = f"about {waiting * st['avg_seconds'] / 60:.0f} min" if st.get("avg_seconds") and waiting else "-"
    detector_html = (
        '<table>'
        f'<tr><td>Status</td><td>{_e(status)}</td></tr>'
        f'<tr><td>Photos waiting to be scanned</td><td>{waiting} (to clear: {backlog})</td></tr>'
        f'<tr><td>Average time per photo (last 50)</td><td>{avg}</td></tr>'
        f'<tr><td>Scanned since the app started</td><td>{st["processed"]}'
        + (f' &middot; last at {_e(st["last_finished"])}' if st.get("last_finished") else '') + '</td></tr>'
        f'<tr><td>Scans that failed</td><td>{failed}'
        + (f' &middot; latest: {_e(st["error"])}' if st.get("error") and st["loaded"] else '') + '</td></tr>'
        f'<tr><td>Photos with 2+ birds</td><td><a href="/gallery">{multi}</a></td></tr>'
        f'<tr><td>Counts as a bird at</td><td>{round(DETECTOR_CONFIG["count_threshold"] * 100)}% detector confidence</td></tr>'
        '</table>')

    # --- Gallery by species (2026-10-20): a photo counts once under EVERY
    # species in it (same rule as the Gallery filter), and "Birds" counts
    # individuals - a House Finch pair is 1 photo, 2 birds. ---
    thr = DETECTOR_CONFIG["count_threshold"]
    photos = c.execute("""SELECT id, COALESCE(species_confirmed, species_aiy), timestamp
                          FROM sightings WHERE review_status='approved'""").fetchall()
    birds = {}
    for sid, sp in c.execute("""SELECT d.sighting_id, COALESCE(d.species_confirmed, d.species_aiy)
                                FROM detections d JOIN sightings s ON s.id = d.sighting_id
                                WHERE s.review_status='approved' AND d.category='animal' AND d.det_conf >= ?
                                  AND COALESCE(d.species_confirmed, '') != '__ignore__'""", (thr,)).fetchall():
        if sp and sp != "background":
            birds.setdefault(sid, []).append(sp)
    agg = {}
    for sid, photo_sp, ts in photos:
        per_bird = birds.get(sid, [])
        names = set(per_bird) or ({photo_sp} if photo_sp and photo_sp != "background" else set())
        for sp in names:
            a = agg.setdefault(sp, [0, 0, ts, ts])
            a[0] += 1
            a[1] += per_bird.count(sp) or 1
            a[2], a[3] = min(a[2], ts), max(a[3], ts)
    rows = [(sp, n, b, first, last) for sp, (n, b, first, last) in agg.items()]
    if rows:
        items = []
        for sp, n, nbirds, first, last in rows:
            # Everything displays as "Common (Latin)": confirmed names are
            # already stored that way; bare scientific names (unconfirmed AIY
            # guesses) get their common name prepended from the lookup.
            if "(" in sp or sp not in common_names:
                label = sp
            else:
                label = f"{common_names[sp]} ({sp})"
            items.append((label, sp, n, nbirds, first[:10], last[:10]))
        items.sort(key=lambda x: (-x[2], x[0].lower()))
        body = "".join(
            f'<tr><td><a href="/gallery?species={quote(sp, safe="")}">{_e(label)}</a></td>'
            f'<td class="num">{n}</td><td class="num">{nb}</td><td>{first}</td><td>{last}</td></tr>'
            for label, sp, n, nb, first, last in items
        )
        species_html = (f'<table><tr><th>Species ({len(items)})</th><th class="num">Photos</th>'
                        f'<th class="num">Birds</th><th>First seen</th><th>Last seen</th></tr>{body}</table>')
    else:
        species_html = '<div class="empty">Nothing in the Gallery yet.</div>'

    src = c.execute("""
        SELECT COALESCE(species_confirmed_source, 'unknown'), COUNT(*)
        FROM sightings WHERE review_status='approved' GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    sources_html = ('<table><tr><th>Name came from</th><th class="num">Photos</th></tr>' +
                    "".join(f'<tr><td>{_e(SOURCE_LABELS.get(s, s))}</td><td class="num">{n}</td></tr>' for s, n in src) +
                    '</table>') if src else '<div class="empty">Nothing in the Gallery yet.</div>'

    daily = c.execute("""
        SELECT substr(timestamp, 1, 10) AS d, COUNT(*),
               SUM(review_status='approved'), SUM(review_status='rejected')
        FROM sightings GROUP BY d ORDER BY d DESC LIMIT 14
    """).fetchall()
    daily_html = ('<table><tr><th>Date</th><th class="num">Photos captured</th>'
                  '<th class="num">Now in Gallery</th><th class="num">Now in Trash</th></tr>' +
                  "".join(f'<tr><td>{d}</td><td class="num">{n}</td><td class="num">{a}</td><td class="num">{r}</td></tr>'
                          for d, n, a, r in daily) +
                  '</table>') if daily else '<div class="empty">No photos yet.</div>'
    conn.close()

    html = (PAGE.replace("__NAV__", NAV_HTML)
                .replace("__PIPELINE__", pipeline_html)
                .replace("__DETECTOR__", detector_html)
                .replace("__SPECIES__", species_html)
                .replace("__SOURCES__", sources_html)
                .replace("__DAILY__", daily_html))
    return HTMLResponse(html)
