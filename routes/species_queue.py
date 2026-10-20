import json as json_module
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML
from routes.boxes import BOXES_CSS, BOXES_JS, DBADGE_CSS

router = APIRouter()

# Non-bird names offered as one-click buttons and in the name autocomplete.
# AIY only knows birds and gives squirrels confident bird names (Mourning
# Dove 0.91, House Sparrow 0.90 - measured 2026-10-20), so mammals are
# named by hand. Values match what SpeciesNet used to write, so old and new
# photos group together in Gallery/Stats.
QUICK_NAMES = [
    ("Fox Squirrel", "Fox Squirrel (Sciurus niger)"),
    ("Gray Squirrel", "Western Gray Squirrel (Sciurus griseus)"),
    ("Cat", "Domestic Cat (Felis catus)"),
]
EXTRA_NAMES = ["Tree Squirrel (sciurus species)", "California Ground Squirrel (Otospermophilus beecheyi)",
               "Domestic Cat (Felis catus)", "Person"]

# Plain template with __PLACEHOLDER__ substitution - no f-string brace
# escaping in the JS.
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
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }
        .q-item { position: relative; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); background: white; }
        .q-item.sel { outline: 3px solid #007bff; }
        .q-check { position: absolute; top: 8px; left: 8px; width: 20px; height: 20px; cursor: pointer; }
        .q-item img { width: 100%; height: 150px; object-fit: cover; display: block; cursor: pointer; }
        .q-caption { padding: 8px; font-size: 12px; }
        button { border: none; border-radius: 4px; font-size: 13px; font-weight: 600; cursor: pointer; padding: 8px 14px; }
        button:disabled { opacity: 0.5; cursor: default; }
        .btn-success { background: #28a745; color: white; }
        .btn-primary { background: #007bff; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-mini { padding: 4px 8px; font-size: 11px; background: rgba(255,255,255,0.15); color: white; }
        .btn-mini.on { background: #ffc107; color: #000; }
        .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.92); align-items: center; justify-content: flex-start; flex-direction: column; padding-top: 30px; overflow-y: auto; }
        .lightbox.active { display: flex; }
        .lb-close { position: fixed; top: 16px; right: 26px; color: white; font-size: 28px; cursor: pointer; user-select: none; }
        .lb-nav { position: fixed; top: 40%; font-size: 28px; padding: 14px 18px; background: rgba(255,255,255,0.15); color: white; }
        .lb-prev { left: 20px; }
        .lb-next { right: 20px; }
        .lb-panel { color: white; margin-top: 14px; width: min(720px, 92vw); }
        .lb-date { font-size: 12px; color: #ccc; margin-bottom: 10px; text-align: center; }
        .bird-row { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
        .bird-num { background: #2ecc71; color: #000; font-weight: 700; font-size: 12px; border-radius: 3px; padding: 2px 6px; min-width: 22px; text-align: center; }
        .bird-row input { flex: 1; min-width: 220px; padding: 7px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
        .bird-row input:disabled { background: #555; color: #aaa; text-decoration: line-through; }
        .aiy-conf { font-size: 11px; color: #ccc; min-width: 70px; }
        .post-row { display: flex; gap: 8px; margin: 12px 0; }
        .post-row button { flex: 1; padding: 10px; font-size: 14px; }
        .waiting { font-size: 13px; color: #ccc; font-style: italic; padding: 6px 0; margin-bottom: 8px; text-align: center; }
        .del-row { display: flex; gap: 6px; }
        .del-row button { flex: 1; }
        __BOXES_CSS__
        .bx-wrap { max-width: 92vw; }
        .bx-wrap img { max-height: 55vh; }
        __DBADGE_CSS__
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
                    <option value="classified">Ready to name</option>
                    <option value="queued">Still scanning</option>
                </select></div>
            <div class="fg"><label>Birds</label>
                <select id="fBirds" onchange="applyView()">
                    <option value="">Any</option>
                    <option value="1">Exactly 1</option>
                    <option value="2">2 or more</option>
                    <option value="0">None found</option>
                </select></div>
            <div class="fg"><label>Search name</label><input type="text" id="fSearch" placeholder="finch, Haemorhous..." oninput="applyView()"></div>
            <div class="fg"><label>Sort</label>
                <select id="fSort" onchange="applyView()">
                    <option value="newest">Newest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="aiyconf">AIY confidence, high first</option>
                    <option value="aiyconf_low">AIY confidence, low first</option>
                    <option value="name">Name A-Z</option>
                </select></div>
            <button class="btn-secondary" onclick="clearFilters()">Clear filters</button>
        </div>

        <div class="controls">
            <button class="btn-secondary" onclick="selectAllShown()">Select all shown</button>
            <button class="btn-secondary" onclick="clearSel()">Clear selection</button>
            <span id="selCount" style="color:#666; font-size:13px; margin-right:auto;"></span>
            <button class="btn-success" id="bAiy" onclick="batch('aiy')" disabled>Post selected with AIY's names</button>
            <button class="btn-secondary" id="bResend" onclick="batch('resend')" disabled>Resend selected</button>
            <button class="btn-danger" id="bDel" onclick="batch('del')" disabled>Delete selected</button>
        </div>

        <div class="grid" id="grid"></div>
    </div>

    <datalist id="nameList">__NAME_OPTIONS__</datalist>

    <div class="lightbox" id="lightbox">
        <span class="lb-close" onclick="closeLightbox()">&times;</span>
        <button class="lb-nav lb-prev" onclick="navLightbox(-1)">&#8592;</button>
        <button class="lb-nav lb-next" onclick="navLightbox(1)">&#8594;</button>
        <div class="bx-wrap"><img id="lbImg"></div>
        <div class="lb-panel" id="lbPanel"></div>
    </div>

    <script>
        __BOXES_JS__
        const queueData = __QUEUE_DATA__;
        const quickNames = __QUICK_NAMES__;
        let view = [];
        let lightboxIndex = -1;
        const selected = new Set();
        // Per-photo edits in the lightbox, kept while you flip between photos:
        // drafts[sightingId][detectionId] = {name, ignored}
        const drafts = {};

        const val = id => document.getElementById(id).value;
        const byId = id => queueData.find(r => r.id === id);

        function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
        function escAttr(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
        function formatWithLatin(common, latin) { return (latin && common && common !== latin) ? `${common} (${latin})` : (common || latin || ''); }
        function aiyLabel(d) { return formatWithLatin(d.common_name, d.species_aiy); }
        function birdsOf(r) { return (r.detections || []).filter(d => d.counted); }
        function photoLabel(r) { return birdSummary(r) || r.aiy_label; }

        // ---------- filtering / sorting ----------
        function applyView() {
            const from = val('fDateFrom'), to = val('fDateTo'), st = val('fStatus'), nb = val('fBirds');
            const q = val('fSearch').trim().toLowerCase();
            view = queueData.filter(r => {
                if (from && r.date < from) return false;
                if (to && r.date > to) return false;
                if (st && r.species_id_status !== st) return false;
                const n = birdsOf(r).length;
                if (nb === '0' && n !== 0) return false;
                if (nb === '1' && n !== 1) return false;
                if (nb === '2' && n < 2) return false;
                if (q) {
                    const hay = [r.aiy_label, r.species_aiy, ...birdsOf(r).flatMap(d => [d.common_name, d.species_aiy])]
                        .filter(Boolean).join(' ').toLowerCase();
                    if (!hay.includes(q)) return false;
                }
                return true;
            });
            const cmp = {
                newest: (a, b) => b.timestamp.localeCompare(a.timestamp),
                oldest: (a, b) => a.timestamp.localeCompare(b.timestamp),
                aiyconf: (a, b) => (b.confidence_aiy ?? -1) - (a.confidence_aiy ?? -1),
                aiyconf_low: (a, b) => (a.confidence_aiy ?? 2) - (b.confidence_aiy ?? 2),
                name: (a, b) => photoLabel(a).localeCompare(photoLabel(b)),
            }[val('fSort')];
            view.sort(cmp);
            const visible = new Set(view.map(r => r.id));
            for (const id of [...selected]) if (!visible.has(id)) selected.delete(id);
            renderGrid();
        }

        function clearFilters() {
            ['fDateFrom', 'fDateTo', 'fStatus', 'fBirds', 'fSearch'].forEach(id => document.getElementById(id).value = '');
            document.getElementById('fSort').value = 'newest';
            applyView();
        }

        function renderGrid() {
            const ready = queueData.filter(r => r.species_id_status === 'classified').length;
            document.getElementById('countLabel').textContent = queueData.length
                ? `${ready} ready to name, ${queueData.length - ready} still being scanned for birds - showing ${view.length}`
                : 'Nothing queued';
            const grid = document.getElementById('grid');
            if (!view.length) {
                grid.innerHTML = `<p style="color:#999; padding:40px; text-align:center;">${queueData.length ? 'Nothing matches these filters.' : 'Queue is empty.'}</p>`;
                updateSel();
                return;
            }
            grid.innerHTML = view.map((r, idx) => {
                const on = selected.has(r.id);
                return `<div class="q-item${on ? ' sel' : ''}" id="card-${r.id}">
                    <input type="checkbox" class="q-check" ${on ? 'checked' : ''} onchange="toggleSel(${r.id}, this.checked)">
                    <img src="/images/${r.filename}" loading="lazy" onclick="openLightbox(${idx})">
                    <div class="q-caption">${detectorBadge(r)} ${esc(photoLabel(r))}<br><small>${r.date}</small></div>
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
            delete drafts[id];
        }

        function aiyBirdsPayload(r) {
            return birdsOf(r).filter(d => d.species_aiy && d.species_aiy !== 'background')
                .map(d => ({ detection_id: d.id, species_confirmed: aiyLabel(d), source: 'aiy' }));
        }

        async function batch(kind) {
            let ids = view.filter(r => selected.has(r.id)).map(r => r.id);
            let skipped = 0;
            if (kind === 'aiy') {
                // Only photos the detector has finished, with at least one named bird
                const ready = ids.filter(id => { const r = byId(id); return r.species_id_status === 'classified' && aiyBirdsPayload(r).length; });
                skipped = ids.length - ready.length;
                ids = ready;
            }
            if (!ids.length) { showInfo('None of the selected photos have AIY names to post yet.'); return; }
            const verb = { aiy: "Post with AIY's names", resend: 'Resend to classifier (back to Manage)', del: 'Delete' }[kind];
            if (!confirm(`${verb}: ${ids.length} photo(s)?` + (skipped ? ` (${skipped} without named birds will be skipped)` : ''))) return;
            let done = 0;
            for (const id of ids) {
                const r = byId(id);
                let res;
                if (kind === 'aiy') {
                    res = await fetch(`/api/sightings/${id}/confirm-species`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ birds: aiyBirdsPayload(r), species_confirmed_source: 'aiy' })
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
        function openLightbox(idx) { lightboxIndex = idx; renderLightbox(); document.getElementById('lightbox').classList.add('active'); }
        function closeLightbox() { document.getElementById('lightbox').classList.remove('active'); lightboxIndex = -1; }
        function navLightbox(delta) {
            if (view.length === 0) return;
            lightboxIndex = (lightboxIndex + delta + view.length) % view.length;
            renderLightbox();
        }

        function draftFor(r) {
            if (!drafts[r.id]) {
                drafts[r.id] = {};
                birdsOf(r).forEach(d => drafts[r.id][d.id] = { name: aiyLabel(d) === 'background' ? '' : aiyLabel(d), ignored: false });
                drafts[r.id].photo = { name: r.species_aiy && r.species_aiy !== 'background' ? formatWithLatin(r.common_name, r.species_aiy) : '' };
            }
            return drafts[r.id];
        }

        function quickButtons(sid, did) {
            return quickNames.map(([short, full]) =>
                `<button class="btn-mini" onclick="setName(${sid}, '${did}', '${escAttr(full).replace(/'/g, "\\'")}')">${esc(short)}</button>`).join('');
        }

        function renderLightbox() {
            if (lightboxIndex < 0 || lightboxIndex >= view.length) { closeLightbox(); return; }
            const r = view[lightboxIndex];
            const img = document.getElementById('lbImg');
            img.src = `/images/${r.filename}`;
            drawBoxes(img, r.detections);
            const draft = draftFor(r);
            const birds = birdsOf(r);
            let panel = `<div class="lb-date">${r.date} &middot; ${detectorBadge(r)} (${lightboxIndex + 1} of ${view.length})
                <span class="bx-toggle" onclick="toggleBoxes(document.getElementById('lbImg'), view[lightboxIndex].detections)">&nbsp; show / hide boxes (b)</span></div>`;

            if (r.detect_status === 'pending') {
                panel += `<div class="waiting">Still scanning this photo for birds - you can name it now or wait.</div>`;
            }
            if (birds.length) {
                birds.forEach((d, i) => {
                    const dr = draft[d.id];
                    const conf = d.confidence_aiy != null ? `AIY ${Math.round(d.confidence_aiy * 100)}%` : 'AIY -';
                    panel += `<div class="bird-row">
                        <span class="bird-num">${i + 1}</span>
                        <input list="nameList" id="name-${d.id}" value="${escAttr(dr.name)}" ${dr.ignored ? 'disabled' : ''}
                               oninput="drafts[${r.id}][${d.id}].name = this.value" placeholder="Name this bird...">
                        <span class="aiy-conf">${conf}</span>
                        ${quickButtons(r.id, d.id)}
                        <button class="btn-mini ${dr.ignored ? 'on' : ''}" onclick="toggleIgnore(${r.id}, ${d.id})" title="Leaf, shadow, reflection...">Not a bird</button>
                    </div>`;
                });
            } else {
                // Detector found nothing countable - one name for the whole photo
                panel += `<div class="bird-row">
                    <input list="nameList" id="name-photo" value="${escAttr(draft.photo.name)}"
                           oninput="drafts[${r.id}].photo.name = this.value" placeholder="No bird found - name it anyway...">
                    ${quickButtons(r.id, 'photo')}
                </div>`;
            }
            panel += `<div class="post-row"><button class="btn-success" onclick="postCurrent()">Post to Gallery (Enter, or Ctrl+Enter while typing)</button></div>
                <div class="del-row">
                    <button class="btn-secondary" onclick="resendToClassifier(${r.id})">Resend to Classifier</button>
                    <button class="btn-danger" onclick="deleteItem(${r.id})">Delete</button>
                </div>`;
            document.getElementById('lbPanel').innerHTML = panel;
        }

        function setName(sid, did, name) {
            const dr = drafts[sid];
            if (did === 'photo') dr.photo.name = name;
            else { dr[did].name = name; dr[did].ignored = false; }
            renderLightbox();
        }
        function toggleIgnore(sid, did) {
            drafts[sid][did].ignored = !drafts[sid][did].ignored;
            renderLightbox();
        }

        async function postCurrent() {
            const r = view[lightboxIndex];
            if (!r) return;
            const draft = draftFor(r);
            const birds = birdsOf(r);
            const body = {};
            if (birds.length) {
                body.birds = birds.map(d => {
                    const dr = draft[d.id];
                    if (dr.ignored) return { detection_id: d.id, species_confirmed: '__ignore__', source: 'ignored' };
                    const name = dr.name.trim();
                    return name ? { detection_id: d.id, species_confirmed: name, source: name === aiyLabel(d) ? 'aiy' : 'custom' } : null;
                });
                if (body.birds.some(b => b === null)) { showInfo('Every bird needs a name (or "Not a bird").'); return; }
                const named = body.birds.filter(b => b.source !== 'ignored');
                if (!named.length) { showInfo('All marked "not a bird" - use Delete if there is nothing here.'); return; }
                // Photo-level name (family page, older views): the first named bird
                body.species_confirmed = named[0].species_confirmed;
                body.species_confirmed_source = named[0].source;
            } else {
                const name = draft.photo.name.trim();
                if (!name) { document.getElementById('name-photo').focus(); return; }
                body.species_confirmed = name;
                body.species_confirmed_source = name === formatWithLatin(r.common_name, r.species_aiy) ? 'aiy' : 'custom';
            }
            const res = await fetch(`/api/sightings/${r.id}/confirm-species`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
            });
            if (!res.ok) { showInfo('Something went wrong - try again.'); return; }
            showInfo(`Posted to Gallery: ${body.birds ? body.birds.filter(b => b.source !== 'ignored').map(b => b.species_confirmed).join(', ') : body.species_confirmed}`);
            removeItem(r.id);
        }

        function removeItem(id) {
            dropItem(id);
            applyView();
            if (view.length === 0) { closeLightbox(); return; }
            if (lightboxIndex >= view.length) lightboxIndex = view.length - 1;
            if (lightboxIndex >= 0) renderLightbox();
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
            showInfo('Resent - back in Manage, and it will be re-scanned for birds');
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
            // Enter posts - but inside a name box only Ctrl+Enter does, since
            // plain Enter there is how you pick an autocomplete suggestion.
            if (e.key === 'Enter' && (e.target.tagName !== 'INPUT' || e.ctrlKey)) { e.preventDefault(); postCurrent(); return; }
            if (e.target.tagName === 'INPUT') return;  // don't hijack keys while typing a name
            if (e.key === 'ArrowLeft') navLightbox(-1);
            else if (e.key === 'ArrowRight') navLightbox(1);
            else if (e.key === 'Escape') closeLightbox();
            else if (e.key === 'b' && lightboxIndex >= 0) toggleBoxes(document.getElementById('lbImg'), view[lightboxIndex].detections);
        });

        applyView();
    </script>
</body>
</html>
"""


@router.get("/species-queue")
async def species_queue_page():
    """Name the birds in photos sent here from Manage. Since 2026-10-20 every
    bird MegaDetector found gets its own row, pre-filled with AIY's guess on
    that bird's crop; a photo reaches the Gallery once it's posted here via
    /confirm-species. Rows and their detections ship to the browser as one
    JSON blob - filtering, sorting and batch actions are client-side."""
    import html as html_module
    import sqlite3
    from main import DB_PATH, common_names, _attach_detections

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, timestamp, species_aiy, confidence_aiy, common_name, "
        "species_id_status, detect_status, animal_count, person_count, max_det_conf "
        "FROM sightings WHERE species_id_status IN ('queued', 'classified') "
        "AND review_status != 'rejected' "
        "ORDER BY timestamp DESC LIMIT 1000"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    _attach_detections(cursor, rows)
    conn.close()

    for r in rows:
        r["aiy_label"] = r["common_name"] or r["species_aiy"] or "Unknown"
        r["date"] = r["timestamp"].split("T")[0]

    names = sorted({f"{c} ({s})" for s, c in common_names.items() if c and s != "background"} | set(EXTRA_NAMES),
                   key=str.lower)
    options = "".join(f'<option value="{html_module.escape(n, quote=True)}">' for n in names)

    html = (PAGE.replace("__BOXES_CSS__", BOXES_CSS).replace("__DBADGE_CSS__", DBADGE_CSS)
                .replace("__BOXES_JS__", BOXES_JS)
                .replace("__NAV__", NAV_HTML)
                .replace("__NAME_OPTIONS__", options)
                .replace("__QUICK_NAMES__", json_module.dumps(QUICK_NAMES))
                .replace("__QUEUE_DATA__", json_module.dumps(rows).replace("<", "\\u003c")))
    return HTMLResponse(html)
