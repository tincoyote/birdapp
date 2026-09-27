import html as html_module
import sqlite3
from urllib.parse import quote
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()

SOURCE_LABELS = {"aiy": "AIY", "sn": "SpeciesNet", "custom": "Typed by you"}

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
        ("/species-queue", one("SELECT COUNT(*) FROM sightings WHERE species_id_status='queued' AND review_status!='rejected'"), "Waiting for laptop run"),
        ("/species-queue", one("SELECT COUNT(*) FROM sightings WHERE species_id_status='classified' AND review_status!='rejected'"), "Ready in Species Queue"),
        ("/gallery", one("SELECT COUNT(*) FROM sightings WHERE review_status='approved'"), "In Gallery"),
        ("/trash", one("SELECT COUNT(*) FROM sightings WHERE review_status='rejected'"), "In Trash"),
    ]
    pipeline_html = "".join(
        f'<a class="card" href="{href}"><div class="n">{n}</div><div class="l">{_e(label)}</div></a>'
        for href, n, label in pipeline
    )

    rows = c.execute("""
        SELECT COALESCE(species_confirmed, species_aiy) AS sp, COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM sightings
        WHERE review_status='approved' AND COALESCE(species_confirmed, species_aiy) IS NOT NULL
        GROUP BY sp
    """).fetchall()
    if rows:
        items = []
        for sp, n, first, last in rows:
            # Everything displays as "Common (Latin)": confirmed names are
            # already stored that way; bare scientific names (unconfirmed AIY
            # guesses) get their common name prepended from the lookup.
            if "(" in sp or sp not in common_names:
                label = sp
            else:
                label = f"{common_names[sp]} ({sp})"
            items.append((label, sp, n, first[:10], last[:10]))
        items.sort(key=lambda x: (-x[2], x[0].lower()))
        body = "".join(
            f'<tr><td><a href="/gallery?species={quote(sp, safe="")}">{_e(label)}</a></td>'
            f'<td class="num">{n}</td><td>{first}</td><td>{last}</td></tr>'
            for label, sp, n, first, last in items
        )
        species_html = (f'<table><tr><th>Species ({len(items)})</th><th class="num">Sightings</th>'
                        f'<th>First seen</th><th>Last seen</th></tr>{body}</table>')
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
                .replace("__SPECIES__", species_html)
                .replace("__SOURCES__", sources_html)
                .replace("__DAILY__", daily_html))
    return HTMLResponse(html)
