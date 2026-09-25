import json as json_module
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()

AGREEMENT_STYLES = {
    "agreed": ("#d4edda", "#155724", "Agreed"),
    "low_confidence": ("#fff3cd", "#856404", "Agreed (low confidence)"),
    "agreed_higher_level": ("#d1ecf1", "#0c5460", "Agreed (family/order)"),
    "inconclusive": ("#e2e3e5", "#383d41", "Inconclusive"),
    "disagreed": ("#f8d7da", "#721c24", "Disagreed"),
    "one_classifier": ("#e2e3e5", "#383d41", "One opinion only"),
    "pending": ("#e2e3e5", "#383d41", "Pending"),
}

# Plain template with __PLACEHOLDER__ substitution (same pattern as manage.py)
# rather than an f-string - the JS here is large enough that doubling every
# brace for f-string escaping was an ongoing source of mistakes.
PAGE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Species ID Queue</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
        h1 { margin-bottom: 10px; font-size: 24px; }
        .subtitle { color: #666; font-size: 14px; margin-bottom: 14px; }
        .info { padding: 12px; background: #e7f3ff; border-left: 4px solid #007bff; margin-bottom: 20px; font-size: 13px; display: none; }
        .filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-bottom: 12px; }
        .fg { display: flex; flex-direction: column; font-size: 12px; color: #555; gap: 3px; }
        .fg input, .fg select { padding: 6px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
        .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 16px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px; }
        .q-item { position: relative; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); background: white; }
        .q-item.sel { outline: 3px solid #007bff; }
        .q-check { position: absolute; top: 8px; left: 8px; width: 20px; height: 20px; cursor: pointer; }
        .q-item img { width: 100%; height: 160px; object-fit: cover; display: block; cursor: pointer; }
        .q-caption { padding: 8px; font-size: 12px; }
        .wait-tag { font-size: 10px; background: #fff3cd; color: #856404; padding: 1px 6px; border-radius: 8px; }
        button { border: none; border-radius: 4px; font-size: 13px; font-weight: 600; cursor: pointer; padding: 8px 14px; }
        button:disabled { opacity: 0.5; cursor: default; }
        .btn-success { background: #28a745; color: white; }
        .btn-primary { background: #007bff; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); align-items: center; justify-content: center; flex-direction: column; }
        .lightbox.active { display: flex; }
        .lb-close { position: absolute; top: 20px; right: 30px; color: white; font-size: 28px; cursor: pointer; user-select: none; }
        .lb-nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 28px; padding: 14px 18px; background: rgba(255,255,255,0.15); color: white; }
        .lb-prev { left: 20px; }
        .lb-next { right: 20px; }
        .lb-img { max-width: 70%; max-height: 55%; border-radius: 4px; }
        .lb-panel { color: white; margin-top: 16px; text-align: center; width: 360px; }
        .lb-date { font-size: 12px; color: #ccc; margin-bottom: 10px; }
        .compare { display: flex; gap: 8px; margin-bottom: 8px; }
        .compare-single { display: block; }
        .opinion { flex: 1; font-size: 14px; font-weight: 600; text-align: center; background: rgba(255,255,255,0.1); border-radius: 4px; padding: 8px; color: white; }
        .src { font-size: 10px; font-weight: 700; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; }
        .conf { font-size: 11px; font-weight: 400; color: #ccc; }
        .raw-guess { font-size: 10px; font-weight: 400; font-style: italic; color: #999; margin-top: 3px; }
        .badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; margin-bottom: 10px; }
        .pick-row { display: flex; gap: 6px; margin-bottom: 8px; }
        .pick-row button { flex: 1; }
        .override-row { display: flex; gap: 6px; margin-bottom: 8px; }
        .override-row input { flex: 1; min-width: 0; padding: 7px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
        .waiting { font-size: 13px; color: #ccc; font-style: italic; padding: 6px 0; margin-bottom: 8px; }
        .del-row { display: flex; gap: 6px; }
        .del-row button { flex: 1; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Species ID Queue</h1>
        __NAV__
        <div class="info" id="info"></div>
        <div class="subtitle" id="countLabel"></div>

        <div class="filters">
            <div class="fg"><label>Date from</label><input type="date" id="fDateFrom" onchange="applyView()"></div>
            <div class="fg"><label>Date to</label><input type="date" id="fDateTo" onchange="applyView()"></div>
            <div class="fg"><label>Status</label>
                <select id="fStatus" onchange="applyView()">
                    <option value="">All</option>
                    <option value="classified">Ready to review</option>
                    <option value="queued">Waiting for second opinion</option>
                </select></div>
            <div class="fg"><label>Agreement</label><select id="fAgree" onchange="applyView()"></select></div>
            <div class="fg"><label>Search name</label><input type="text" id="fSearch" placeholder="finch, Haemorhous..." oninput="applyView()"></div>
            <div class="fg"><label>Sort</label>
                <select id="fSort" onchange="applyView()">
                    <option value="newest">Newest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="aiyconf">AIY confidence (high first)</option>
                    <option value="snconf">SpeciesNet confidence (high first)</option>
                    <option value="name">AIY name A-Z</option>
                </select></div>
            <button class="btn-secondary" onclick="clearFilters()">Clear filters</button>
        </div>

        <div class="controls">
            <button class="btn-secondary" onclick="selectAllShown()">Select all shown</button>
            <button class="btn-secondary" onclick="clearSel()">Clear selection</button>
            <span id="selCount" style="color:#666; font-size:13px; margin-right:auto;"></span>
            <button class="btn-success" id="bAiy" onclick="batch('aiy')" disabled>Post selected as AIY</button>
            <button class="btn-secondary" id="bResend" onclick="batch('resend')" disabled>Resend selected</button>
            <button class="btn-danger" id="bDel" onclick="batch('del')" disabled>Delete selected</button>
        </div>

        <div class="grid" id="grid"></div>
    </div>

    <div class="lightbox" id="lightbox">
        <span class="lb-close" onclick="closeLightbox()">&times;</span>
        <button class="lb-nav lb-prev" onclick="navLightbox(-1)">&#8592;</button>
        <button class="lb-nav lb-next" onclick="navLightbox(1)">&#8594;</button>
        <img class="lb-img" id="lbImg">
        <div class="lb-panel" id="lbPanel"></div>
    </div>

    <script>
        const queueData = __QUEUE_DATA__;
        const agreementStyles = __AGREEMENT_STYLES__;
        let view = [];            // queueData after filter + sort; grid and lightbox both index into this
        let lightboxIndex = -1;
        const selected = new Set();

        const val = id => document.getElementById(id).value;
        const byId = id => queueData.find(r => r.id === id);

        function esc(s) {
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }
        function escAttr(s) {
            // esc() doesn't escape " - needed inside double-quoted attributes
            return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }
        function formatWithLatin(common, latin) {
            // "Common Name (Latin)" - skipped when they're the same (e.g. a rollup like "bird")
            return (latin && common !== latin) ? `${common} (${latin})` : common;
        }

        // ---------- filtering / sorting ----------
        (function initAgreementFilter() {
            const sel = document.getElementById('fAgree');
            sel.innerHTML = '<option value="">All</option>' +
                Object.entries(agreementStyles).map(([k, v]) => `<option value="${k}">${esc(v.text)}</option>`).join('');
        })();

        function applyView() {
            const from = val('fDateFrom'), to = val('fDateTo'), st = val('fStatus'), ag = val('fAgree');
            const q = val('fSearch').trim().toLowerCase();
            view = queueData.filter(r => {
                if (from && r.date < from) return false;
                if (to && r.date > to) return false;
                if (st && r.species_id_status !== st) return false;
                if (ag && r.classifier_agreement !== ag) return false;
                if (q) {
                    const hay = [r.aiy_label, r.species_aiy, r.inat_label, r.species_inat, r.species_inat_raw_guess]
                        .filter(Boolean).join(' ').toLowerCase();
                    if (!hay.includes(q)) return false;
                }
                return true;
            });
            const cmp = {
                newest: (a, b) => b.timestamp.localeCompare(a.timestamp),
                oldest: (a, b) => a.timestamp.localeCompare(b.timestamp),
                aiyconf: (a, b) => (b.confidence_aiy ?? -1) - (a.confidence_aiy ?? -1),
                snconf: (a, b) => (b.confidence_inat ?? -1) - (a.confidence_inat ?? -1),
                name: (a, b) => (a.aiy_label || '').localeCompare(b.aiy_label || ''),
            }[val('fSort')];
            view.sort(cmp);
            // Never act on photos the filter is hiding - drop them from the selection
            const visible = new Set(view.map(r => r.id));
            for (const id of [...selected]) if (!visible.has(id)) selected.delete(id);
            renderGrid();
        }

        function clearFilters() {
            ['fDateFrom', 'fDateTo', 'fStatus', 'fAgree', 'fSearch'].forEach(id => document.getElementById(id).value = '');
            document.getElementById('fSort').value = 'newest';
            applyView();
        }

        function renderGrid() {
            const classified = queueData.filter(r => r.species_id_status === 'classified').length;
            document.getElementById('countLabel').textContent = queueData.length
                ? `${classified} ready to review, ${queueData.length - classified} waiting for a second opinion - showing ${view.length}`
                : 'Nothing queued';
            const grid = document.getElementById('grid');
            if (!view.length) {
                grid.innerHTML = `<p style="color:#999; padding:40px; text-align:center;">${queueData.length ? 'Nothing matches these filters.' : 'Queue is empty.'}</p>`;
                updateSel();
                return;
            }
            grid.innerHTML = view.map((r, idx) => {
                const label = r.inat_label ? `${r.aiy_label} / ${r.inat_label}` : r.aiy_label;
                const wait = r.species_id_status === 'classified' ? '' : ' <span class="wait-tag">waiting</span>';
                const on = selected.has(r.id);
                return `<div class="q-item${on ? ' sel' : ''}" id="card-${r.id}">
                    <input type="checkbox" class="q-check" ${on ? 'checked' : ''} onchange="toggleSel(${r.id}, this.checked)">
                    <img src="/images/${r.filename}" loading="lazy" onclick="openLightbox(${idx})">
                    <div class="q-caption">${esc(label)}${wait}<br><small>${r.date}</small></div>
                </div>`;
            }).join('');
            updateSel();
        }

        // ---------- selection / batch ----------
        function toggleSel(id, on) {
            on ? selected.add(id) : selected.delete(id);
            const card = document.getElementById('card-' + id);
            if (card) card.classList.toggle('sel', on);
            updateSel();
        }
        function selectAllShown() { view.forEach(r => selected.add(r.id)); renderGrid(); }
        function clearSel() { selected.clear(); renderGrid(); }
        function updateSel() {
            document.getElementById('selCount').textContent = selected.size ? `${selected.size} selected` : '';
            ['bAiy', 'bResend', 'bDel'].forEach(id => document.getElementById(id).disabled = selected.size === 0);
        }

        function dropItem(id) {
            const i = queueData.findIndex(x => x.id === id);
            if (i !== -1) queueData.splice(i, 1);
            selected.delete(id);
        }

        async function batch(kind) {
            let ids = view.filter(r => selected.has(r.id)).map(r => r.id);
            let skipped = 0;
            if (kind === 'aiy') {
                // Only classified photos have the crop-based AIY result worth posting
                const ready = ids.filter(id => byId(id).species_id_status === 'classified');
                skipped = ids.length - ready.length;
                ids = ready;
            }
            if (!ids.length) { showInfo('None of the selected photos are ready for that yet.'); return; }
            const verb = { aiy: 'Post as AIY', resend: 'Resend to classifier (back to Manage)', del: 'Delete' }[kind];
            if (!confirm(`${verb}: ${ids.length} photo(s)?` + (skipped ? ` (${skipped} still waiting will be skipped)` : ''))) return;
            let done = 0;
            for (const id of ids) {
                const r = byId(id);
                let res;
                if (kind === 'aiy') {
                    res = await fetch(`/api/sightings/${id}/confirm-species`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ species_confirmed: formatWithLatin(r.aiy_label, r.species_aiy), species_confirmed_source: 'aiy' })
                    });
                } else if (kind === 'resend') {
                    res = await fetch(`/api/sightings/${id}/resend-classifier`, { method: 'POST' });
                } else {
                    res = await fetch(`/api/sightings/${id}/review-status`, {
                        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ review_status: 'rejected' })
                    });
                }
                if (res.ok) { dropItem(id); done++; }
            }
            showInfo(`${verb}: ${done} of ${ids.length} done` + (done < ids.length ? ' - some failed, still shown' : ''));
            applyView();
        }

        // ---------- lightbox ----------
        function openLightbox(idx) {
            lightboxIndex = idx;
            renderLightbox();
            document.getElementById('lightbox').classList.add('active');
        }
        function closeLightbox() {
            document.getElementById('lightbox').classList.remove('active');
            lightboxIndex = -1;
        }
        function navLightbox(delta) {
            if (view.length === 0) return;
            lightboxIndex = (lightboxIndex + delta + view.length) % view.length;
            renderLightbox();
        }

        function renderLightbox() {
            if (lightboxIndex < 0 || lightboxIndex >= view.length) { closeLightbox(); return; }
            const r = view[lightboxIndex];
            document.getElementById('lbImg').src = `/images/${r.filename}`;

            const aiyConf = r.confidence_aiy != null ? Math.round(r.confidence_aiy * 100) + '%' : '?';
            let panel = `<div class="lb-date">${r.date} (${lightboxIndex + 1} of ${view.length})</div>`;

            if (r.species_id_status === 'classified') {
                const inatConf = r.confidence_inat != null ? Math.round(r.confidence_inat * 100) + '%' : '?';
                const st = agreementStyles[r.classifier_agreement] || { bg: '#e2e3e5', fg: '#383d41', text: r.classifier_agreement || '' };
                const raw = r.species_inat_raw_guess
                    ? `<div class="raw-guess">raw top guess: ${esc(r.species_inat_raw_guess)} (${Math.round(r.confidence_inat_raw * 100)}%)</div>` : '';
                panel += `
                    <div class="compare">
                        <div class="opinion"><div class="src">AIY</div>${esc(r.aiy_label)}<div class="conf">${aiyConf}</div></div>
                        <div class="opinion"><div class="src">SpeciesNet</div>${esc(r.inat_label)}<div class="conf">${inatConf}</div>${raw}</div>
                    </div>
                    <span class="badge" style="background:${st.bg}; color:${st.fg};">${esc(st.text)}</span>
                    <div class="pick-row">
                        <button class="btn-success" data-id="${r.id}" data-source="aiy" data-label="${escAttr(formatWithLatin(r.aiy_label, r.species_aiy))}" onclick="pickBtn(this)">Post as AIY</button>
                        <button class="btn-primary" data-id="${r.id}" data-source="sn" data-label="${escAttr(formatWithLatin(r.inat_label, r.species_inat))}" onclick="pickBtn(this)">Post as SpeciesNet</button>
                    </div>
                    <div class="override-row">
                        <input type="text" id="lbOverride" placeholder="Something else...">
                        <button class="btn-secondary" onclick="pickOverride(${r.id})">Post</button>
                    </div>
                `;
            } else {
                panel += `
                    <div class="compare compare-single">
                        <div class="opinion"><div class="src">AIY</div>${esc(r.aiy_label)}<div class="conf">${aiyConf}</div></div>
                    </div>
                    <div class="waiting">Waiting for second opinion</div>
                `;
            }
            panel += `<div class="del-row">
                <button class="btn-secondary" onclick="resendToClassifier(${r.id})">Resend to Classifier</button>
                <button class="btn-danger" onclick="deleteItem(${r.id})">Delete</button>
            </div>`;
            document.getElementById('lbPanel').innerHTML = panel;
        }

        function removeItem(id) {
            // Acting on the viewed photo: after removal the next photo slides into
            // this same index, so lightboxIndex stays put (clamped at the end).
            dropItem(id);
            applyView();
            if (view.length === 0) { closeLightbox(); return; }
            if (lightboxIndex >= view.length) lightboxIndex = view.length - 1;
            if (lightboxIndex >= 0) renderLightbox();
        }

        function pickBtn(btn) { pick(parseInt(btn.dataset.id, 10), btn.dataset.label, btn.dataset.source); }

        async function pick(id, label, source) {
            const res = await fetch(`/api/sightings/${id}/confirm-species`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ species_confirmed: label, species_confirmed_source: source })
            });
            if (!res.ok) { showInfo('Something went wrong - try again.'); return; }
            showInfo(`Posted to Gallery: ${label}`);
            removeItem(id);
        }

        function pickOverride(id) {
            const input = document.getElementById('lbOverride');
            const value = input.value.trim();
            if (!value) { input.focus(); return; }
            pick(id, value, 'custom');
        }

        async function deleteItem(id) {
            await fetch(`/api/sightings/${id}/review-status`, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ review_status: 'rejected' })
            });
            showInfo('Sent to trash');
            removeItem(id);
        }

        async function resendToClassifier(id) {
            await fetch(`/api/sightings/${id}/resend-classifier`, { method: 'POST' });
            showInfo('Resent to classifier - back in Manage for a fresh look');
            removeItem(id);
        }

        function showInfo(msg) {
            const info = document.getElementById('info');
            info.textContent = msg;
            info.style.display = 'block';
            setTimeout(() => info.style.display = 'none', 4000);
        }

        document.addEventListener('keydown', e => {
            if (!document.getElementById('lightbox').classList.contains('active')) return;
            if (e.target.tagName === 'INPUT') return;  // don't hijack arrows while typing an override
            if (e.key === 'ArrowLeft') navLightbox(-1);
            else if (e.key === 'ArrowRight') navLightbox(1);
            else if (e.key === 'Escape') closeLightbox();
        });

        applyView();
    </script>
</body>
</html>
"""


@router.get("/species-queue")
async def species_queue_page():
    """Compare-and-pick UI for sightings queued for (or finished with) the
    second-opinion run. This page is the Gallery entry point: Manage is only
    the bird/no-bird screen, and a photo reaches the Gallery once a human
    picks a species here via /confirm-species.

    All rows ship to the browser as an embedded JSON blob; filtering, sorting,
    selection and batch actions (2026-09-23) all happen client-side on that
    data, so the grid and lightbox navigation need no extra round-trips."""
    import sqlite3
    from main import DB_PATH, common_names

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, timestamp, species_aiy, confidence_aiy, common_name, "
        "species_inat, confidence_inat, classifier_agreement, species_id_status, "
        "species_inat_raw_guess, confidence_inat_raw "
        "FROM sightings WHERE species_id_status IN ('queued', 'classified') "
        "AND review_status != 'rejected' "
        "ORDER BY timestamp DESC LIMIT 1000"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["aiy_label"] = r["common_name"] or r["species_aiy"] or "Unknown"
        r["inat_label"] = (common_names.get(r["species_inat"], r["species_inat"]) or "Unknown") \
            if r["species_id_status"] == "classified" else None
        r["date"] = r["timestamp"].split("T")[0]

    queue_data_json = json_module.dumps(rows).replace("<", "\\u003c")
    agreement_styles_json = json_module.dumps(
        {k: {"bg": v[0], "fg": v[1], "text": v[2]} for k, v in AGREEMENT_STYLES.items()}
    )
    html = (PAGE.replace("__AGREEMENT_STYLES__", agreement_styles_json)
                .replace("__NAV__", NAV_HTML)
                .replace("__QUEUE_DATA__", queue_data_json))
    return HTMLResponse(html)
