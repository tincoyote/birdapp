import html as html_module
import json as json_module
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()

AGREEMENT_STYLES = {
    "agreed": ("#d4edda", "#155724", "Agreed"),
    "low_confidence": ("#fff3cd", "#856404", "Agreed (low confidence)"),
    "inconclusive": ("#e2e3e5", "#383d41", "Inconclusive"),
    "disagreed": ("#f8d7da", "#721c24", "Disagreed"),
    "one_classifier": ("#e2e3e5", "#383d41", "One opinion only"),
    "pending": ("#e2e3e5", "#383d41", "Pending"),
}


@router.get("/species-queue")
async def species_queue_page():
    """Compare-and-pick UI for sightings that have gone through the second
    classifier (SpeciesNet, run off-box - see run_second_opinion.py) or are
    still waiting for it. Under the revised flow this page IS the Gallery
    entry point: Manage only cleanses the incoming feed (keep/reject junk)
    and no longer approves anything directly - a photo reaches the Gallery
    only once a human picks a winning species here, via /confirm-species.

    Grid cards are deliberately minimal (image + caption only) - all
    comparison and action UI lives in the lightbox, matching Manage/Gallery's
    existing pattern of "small thumbnails to browse, big modal to act."
    Row data ships as an embedded JSON blob so lightbox navigation needs no
    second round-trip and can apply the same review_status != 'rejected'
    filter the generic /api/sightings endpoint can't express (it has no
    "not equal" filter, only exact-match)."""
    import sqlite3
    from main import DB_PATH, common_names

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, timestamp, species_aiy, confidence_aiy, common_name, "
        "species_inat, confidence_inat, classifier_agreement, species_id_status "
        "FROM sightings WHERE species_id_status IN ('queued', 'classified') "
        "AND review_status != 'rejected' "
        "ORDER BY CASE WHEN species_id_status = 'classified' THEN 0 ELSE 1 END, "
        "timestamp DESC LIMIT 200"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["aiy_label"] = r["common_name"] or r["species_aiy"] or "Unknown"
        r["inat_label"] = (common_names.get(r["species_inat"], r["species_inat"]) or "Unknown") \
            if r["species_id_status"] == "classified" else None
        r["date"] = r["timestamp"].split("T")[0]

    classified_count = sum(1 for r in rows if r["species_id_status"] == "classified")
    queued_count = len(rows) - classified_count

    cards = ""
    for idx, r in enumerate(rows):
        label = r["inat_label"] and f"{r['aiy_label']} / {r['inat_label']}" or r["aiy_label"]
        cards += f"""
            <div class="q-item" id="card-{r['id']}" onclick="openLightbox({idx})">
                <img src="/images/{r['filename']}">
                <div class="q-caption">{html_module.escape(label)}<br><small>{r['date']}</small></div>
            </div>
        """

    empty_msg = '<p style="color:#999; padding:40px; text-align:center;">Queue is empty.</p>'
    body_grid = cards if rows else empty_msg
    count_label = (
        f"{classified_count} ready to review, {queued_count} waiting for a second opinion"
        if rows else "Nothing queued"
    )
    queue_data_json = json_module.dumps(rows).replace("<", "\\u003c")
    agreement_styles_json = json_module.dumps(
        {k: {"bg": v[0], "fg": v[1], "text": v[2]} for k, v in AGREEMENT_STYLES.items()}
    )

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
            .info {{ padding: 12px; background: #e7f3ff; border-left: 4px solid #007bff; margin-bottom: 20px; font-size: 13px; display: none; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px; }}
            .q-item {{ border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); background: white; cursor: pointer; }}
            .q-item img {{ width: 100%; height: 160px; object-fit: cover; display: block; }}
            .q-caption {{ padding: 8px; font-size: 12px; }}
            button {{ border: none; border-radius: 4px; font-size: 13px; font-weight: 600; cursor: pointer; padding: 8px 14px; }}
            .btn-success {{ background: #28a745; color: white; }}
            .btn-primary {{ background: #007bff; color: white; }}
            .btn-secondary {{ background: #6c757d; color: white; }}
            .btn-danger {{ background: #dc3545; color: white; }}
            .lightbox {{ display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); align-items: center; justify-content: center; flex-direction: column; }}
            .lightbox.active {{ display: flex; }}
            .lb-close {{ position: absolute; top: 20px; right: 30px; color: white; font-size: 28px; cursor: pointer; user-select: none; }}
            .lb-nav {{ position: absolute; top: 50%; transform: translateY(-50%); font-size: 28px; padding: 14px 18px; background: rgba(255,255,255,0.15); color: white; }}
            .lb-prev {{ left: 20px; }}
            .lb-next {{ right: 20px; }}
            .lb-img {{ max-width: 70%; max-height: 55%; border-radius: 4px; }}
            .lb-panel {{ color: white; margin-top: 16px; text-align: center; width: 360px; }}
            .lb-date {{ font-size: 12px; color: #ccc; margin-bottom: 10px; }}
            .compare {{ display: flex; gap: 8px; margin-bottom: 8px; }}
            .compare-single {{ display: block; }}
            .opinion {{ flex: 1; font-size: 14px; font-weight: 600; text-align: center; background: rgba(255,255,255,0.1); border-radius: 4px; padding: 8px; color: white; }}
            .src {{ font-size: 10px; font-weight: 700; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; }}
            .conf {{ font-size: 11px; font-weight: 400; color: #ccc; }}
            .badge {{ display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; margin-bottom: 10px; }}
            .pick-row {{ display: flex; gap: 6px; margin-bottom: 8px; }}
            .pick-row button {{ flex: 1; }}
            .override-row {{ display: flex; gap: 6px; margin-bottom: 8px; }}
            .override-row input {{ flex: 1; min-width: 0; padding: 7px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }}
            .waiting {{ font-size: 13px; color: #ccc; font-style: italic; padding: 6px 0; margin-bottom: 8px; }}
            .del-row button {{ width: 100%; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Species ID Queue</h1>
            {NAV_HTML}
            <div class="info" id="info"></div>
            <div class="subtitle">{count_label}</div>
            <div class="grid">
                {body_grid}
            </div>
        </div>

        <div class="lightbox" id="lightbox">
            <span class="lb-close" onclick="closeLightbox()">&times;</span>
            <button class="lb-nav lb-prev" onclick="navLightbox(-1)">&#8592;</button>
            <button class="lb-nav lb-next" onclick="navLightbox(1)">&#8594;</button>
            <img class="lb-img" id="lbImg">
            <div class="lb-panel" id="lbPanel"></div>
        </div>

        <script>
            const queueData = {queue_data_json};
            const agreementStyles = {agreement_styles_json};
            let lightboxIndex = -1;

            function esc(s) {{
                const d = document.createElement('div');
                d.textContent = s;
                return d.innerHTML;
            }}

            function escAttr(s) {{
                // esc() above is safe for TEXT content but does NOT escape
                // literal " characters - innerHTML only escapes &, <, > in
                // text nodes, since quotes aren't special there. Embedding
                // into a double-quoted HTML attribute needs " escaped too,
                // or the exact bug that broke the pick buttons happens
                // again the moment any label contains one.
                return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            }}

            function openLightbox(idx) {{
                lightboxIndex = idx;
                renderLightbox();
                document.getElementById('lightbox').classList.add('active');
            }}
            function closeLightbox() {{
                document.getElementById('lightbox').classList.remove('active');
                lightboxIndex = -1;
            }}
            function navLightbox(delta) {{
                if (queueData.length === 0) return;
                lightboxIndex = (lightboxIndex + delta + queueData.length) % queueData.length;
                renderLightbox();
            }}

            function renderLightbox() {{
                if (lightboxIndex < 0 || lightboxIndex >= queueData.length) {{ closeLightbox(); return; }}
                const r = queueData[lightboxIndex];
                document.getElementById('lbImg').src = `/images/${{r.filename}}`;

                const aiyConf = r.confidence_aiy != null ? Math.round(r.confidence_aiy * 100) + '%' : '?';
                let panel = `<div class="lb-date">${{r.date}} (${{lightboxIndex + 1}} of ${{queueData.length}})</div>`;

                if (r.species_id_status === 'classified') {{
                    const inatConf = r.confidence_inat != null ? Math.round(r.confidence_inat * 100) + '%' : '?';
                    const st = agreementStyles[r.classifier_agreement] || {{bg: '#e2e3e5', fg: '#383d41', text: r.classifier_agreement || ''}};
                    panel += `
                        <div class="compare">
                            <div class="opinion"><div class="src">AIY</div>${{esc(r.aiy_label)}}<div class="conf">${{aiyConf}}</div></div>
                            <div class="opinion"><div class="src">SpeciesNet</div>${{esc(r.inat_label)}}<div class="conf">${{inatConf}}</div></div>
                        </div>
                        <span class="badge" style="background:${{st.bg}}; color:${{st.fg}};">${{st.text}}</span>
                        <div class="pick-row">
                            <button class="btn-success" data-id="${{r.id}}" data-label="${{escAttr(r.aiy_label)}}" onclick="pickBtn(this)">Post as AIY</button>
                            <button class="btn-primary" data-id="${{r.id}}" data-label="${{escAttr(r.inat_label)}}" onclick="pickBtn(this)">Post as SpeciesNet</button>
                        </div>
                        <div class="override-row">
                            <input type="text" id="lbOverride" placeholder="Something else...">
                            <button class="btn-secondary" onclick="pickOverride(${{r.id}})">Post</button>
                        </div>
                    `;
                }} else {{
                    panel += `
                        <div class="compare compare-single">
                            <div class="opinion"><div class="src">AIY</div>${{esc(r.aiy_label)}}<div class="conf">${{aiyConf}}</div></div>
                        </div>
                        <div class="waiting">Waiting for second opinion</div>
                    `;
                }}
                panel += `<div class="del-row"><button class="btn-danger" onclick="deleteItem(${{r.id}})">Delete</button></div>`;
                document.getElementById('lbPanel').innerHTML = panel;
            }}

            function removeItem(id) {{
                const idx = queueData.findIndex(x => x.id === id);
                if (idx === -1) return;
                queueData.splice(idx, 1);
                const card = document.getElementById('card-' + id);
                if (card) card.remove();
                if (queueData.length === 0) {{ closeLightbox(); return; }}
                // Deleting/picking always acts on the currently-viewed item
                // (idx === lightboxIndex), so lightboxIndex should just stay
                // put after the splice - the item that was "next" shifts
                // down into this same slot automatically. The old code had
                // an extra decrement branch here that fired on every single
                // delete (since idx <= lightboxIndex is always true for the
                // current item) and sent the lightbox backward to whatever
                // was shown before, instead of forward to what's next.
                if (lightboxIndex >= queueData.length) lightboxIndex = queueData.length - 1;
                renderLightbox();
            }}

            function pickBtn(btn) {{
                pick(parseInt(btn.dataset.id, 10), btn.dataset.label);
            }}

            async function pick(id, label) {{
                const res = await fetch(`/api/sightings/${{id}}/confirm-species`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{species_confirmed: label}})
                }});
                if (!res.ok) {{ showInfo('Something went wrong - try again.'); return; }}
                showInfo(`Posted to Gallery: ${{label}}`);
                removeItem(id);
            }}

            function pickOverride(id) {{
                const input = document.getElementById('lbOverride');
                const value = input.value.trim();
                if (!value) {{ input.focus(); return; }}
                pick(id, value);
            }}

            async function deleteItem(id) {{
                await fetch(`/api/sightings/${{id}}/review-status`, {{
                    method: 'PATCH',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{review_status: 'rejected'}})
                }});
                showInfo('Sent to trash');
                removeItem(id);
            }}

            function showInfo(msg) {{
                const info = document.getElementById('info');
                info.textContent = msg;
                info.style.display = 'block';
                setTimeout(() => info.style.display = 'none', 4000);
            }}

            document.addEventListener('keydown', e => {{
                if (!document.getElementById('lightbox').classList.contains('active')) return;
                if (e.key === 'ArrowLeft') navLightbox(-1);
                else if (e.key === 'ArrowRight') navLightbox(1);
                else if (e.key === 'Escape') closeLightbox();
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

