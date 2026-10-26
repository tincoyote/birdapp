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
# The whole queue ships to the browser at once (filters are client-side).
# Raised from 1000 on 2026-10-25, when Manage's backlog moved in here.
QUEUE_LIMIT = 3000

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
        /* Name picker (2026-10-25): replaces the browser's <datalist>, whose
           arrow only listed names matching what was already in the box. */
        .nm-wrap { position: relative; flex: 1; min-width: 220px; display: flex; }
        .nm-wrap input { border-top-right-radius: 0 !important; border-bottom-right-radius: 0 !important; }
        .nm-arrow { padding: 0 10px; border-radius: 0 4px 4px 0; background: #e9ecef; color: #333; font-size: 12px; }
        .nm-list { display: none; position: absolute; top: 100%; left: 0; right: 0; max-height: 260px; overflow-y: auto;
                   background: white; color: #222; border: 1px solid #999; border-radius: 0 0 4px 4px; z-index: 1000;
                   font-size: 13px; text-align: left; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }
        .nm-list.open { display: block; }
        .nm-opt { padding: 5px 8px; cursor: pointer; }
        .nm-opt.hi { background: #007bff; color: white; }
        .nm-none { padding: 6px 8px; color: #888; font-style: italic; }
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
            <div class="fg" style="min-width:220px"><label>Species confidence: <span id="confLabel">0% - 100%</span> <span style="color:#999">(least sure bird)</span></label>
                <div style="display:flex; gap:6px">
                    <input type="range" id="fConfMin" min="0" max="100" value="0" oninput="applyView()" style="width:100%">
                    <input type="range" id="fConfMax" min="0" max="100" value="100" oninput="applyView()" style="width:100%">
                </div></div>
            <div class="fg" style="min-width:220px"><label>Bird confidence: <span id="detLabel">0% - 100%</span> <span style="color:#999">(is it a bird)</span></label>
                <div style="display:flex; gap:6px">
                    <input type="range" id="fDetMin" min="0" max="100" value="0" oninput="applyView()" style="width:100%">
                    <input type="range" id="fDetMax" min="0" max="100" value="100" oninput="applyView()" style="width:100%">
                </div></div>
            <div class="fg"><label>Search name</label><input type="text" id="fSearch" placeholder="finch, Haemorhous..." oninput="applyView()"></div>
            <div class="fg"><label>Sort</label>
                <select id="fSort" onchange="applyView()">
                    <option value="newest">Newest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="aiyconf">Species confidence, high first</option>
                    <option value="aiyconf_low">Species confidence, low first</option>
                    <option value="detconf">Bird confidence, high first</option>
                    <option value="detconf_low">Bird confidence, low first</option>
                    <option value="name">Name A-Z</option>
                </select></div>
            <button class="btn-secondary" onclick="clearFilters()">Clear filters</button>
        </div>

        <div class="controls">
            <button class="btn-secondary" onclick="selectAllShown()">Select all shown</button>
            <button class="btn-secondary" onclick="clearSel()">Clear selection</button>
            <span id="selCount" style="color:#666; font-size:13px; margin-right:auto;"></span>
            <button class="btn-success" id="bAiy" onclick="batch('aiy')" disabled>Post selected with AIY's names</button>
            <button class="btn-secondary" id="bResend" onclick="batch('resend')" disabled>Re-scan selected</button>
            <button class="btn-danger" id="bDel" onclick="batch('del')" disabled>Delete selected</button>
        </div>

        <div class="grid" id="grid"></div>
    </div>


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
        const queueTotal = __QUEUE_TOTAL__;
        const quickNames = __QUICK_NAMES__;
        let view = [];
        let lightboxIndex = -1;
        const selected = new Set();
        // Per-photo edits in the lightbox, kept while you flip between photos:
        // drafts[sightingId][detectionId] = {name}  (exclusions are saved to the server immediately)
        const drafts = {};

        const val = id => document.getElementById(id).value;
        const byId = id => queueData.find(r => r.id === id);

        function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
        function escAttr(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
        function formatWithLatin(common, latin) { return (latin && common && common !== latin) ? `${common} (${latin})` : (common || latin || ''); }
        function aiyLabel(d) { return formatWithLatin(d.common_name, d.species_aiy); }
        function birdsOf(r) { return (r.detections || []).filter(d => d.counted); }
        function photoLabel(r) { return birdSummary(r) || r.aiy_label; }
        // Species confidence of the photo = its LEAST certain bird, so a
        // confident finch can't hide an unsure jay next to it. Photos with
        // no bird box fall back to the photo-level AIY guess.
        function speciesConf(r) {
            const c = birdsOf(r).map(d => d.confidence_aiy).filter(v => v != null);
            return c.length ? Math.min(...c) : r.confidence_aiy;
        }
        function syncPair(minId, maxId, labelId) {
            let a = +val(minId), b = +val(maxId);
            if (a > b) [a, b] = [b, a];
            document.getElementById(labelId).textContent = `${a}% - ${b}%`;
            return [a, b];
        }
        const syncConf = () => syncPair('fConfMin', 'fConfMax', 'confLabel');
        // Bird confidence (2026-10-25) = the detector's confidence in the
        // photo's most likely animal - the "is there a bird" number Manage
        // used to filter on. Photos still being scanned have none yet.
        function birdConf(r) { return r.detect_status === 'done' ? (r.max_det_conf || 0) : null; }

        // ---------- filtering / sorting ----------
        function applyView() {
            const from = val('fDateFrom'), to = val('fDateTo'), st = val('fStatus'), nb = val('fBirds');
            const q = val('fSearch').trim().toLowerCase();
            const [cMin, cMax] = syncConf();
            const confOn = cMin > 0 || cMax < 100;
            const [dMin, dMax] = syncPair('fDetMin', 'fDetMax', 'detLabel');
            const detOn = dMin > 0 || dMax < 100;
            view = queueData.filter(r => {
                if (confOn) {
                    const c = speciesConf(r);
                    if (c == null || c * 100 < cMin || c * 100 > cMax) return false;
                }
                if (detOn) {
                    const c = birdConf(r);
                    if (c == null || c * 100 < dMin || c * 100 > dMax) return false;
                }
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
                aiyconf: (a, b) => (speciesConf(b) ?? -1) - (speciesConf(a) ?? -1),
                aiyconf_low: (a, b) => (speciesConf(a) ?? 2) - (speciesConf(b) ?? 2),
                detconf: (a, b) => (birdConf(b) ?? -1) - (birdConf(a) ?? -1),
                detconf_low: (a, b) => (birdConf(a) ?? 2) - (birdConf(b) ?? 2),
                name: (a, b) => photoLabel(a).localeCompare(photoLabel(b)),
            }[val('fSort')];
            view.sort(cmp);
            const visible = new Set(view.map(r => r.id));
            for (const id of [...selected]) if (!visible.has(id)) selected.delete(id);
            renderGrid();
        }

        function clearFilters() {
            ['fDateFrom', 'fDateTo', 'fStatus', 'fBirds', 'fSearch'].forEach(id => document.getElementById(id).value = '');
            ['fConfMin', 'fDetMin'].forEach(id => document.getElementById(id).value = 0);
            ['fConfMax', 'fDetMax'].forEach(id => document.getElementById(id).value = 100);
            document.getElementById('fSort').value = 'newest';
            applyView();
        }

        function renderGrid() {
            const ready = queueData.filter(r => r.species_id_status === 'classified').length;
            document.getElementById('countLabel').textContent = queueData.length
                ? `${ready} ready to name, ${queueData.length - ready} still being scanned for birds - showing ${view.length}`
                  + (queueTotal > queueData.length ? ` (newest ${queueData.length} of ${queueTotal} loaded - clear some and reload for the rest)` : '')
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
            const verb = { aiy: "Post with AIY's names", resend: 'Re-scan for birds', del: 'Delete' }[kind];
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
                    if (res.ok) { markRescanning(id); done++; }
                    continue;
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
            if (!drafts[r.id]) drafts[r.id] = { photo: { name: r.species_aiy && r.species_aiy !== 'background' ? formatWithLatin(r.common_name, r.species_aiy) : '' } };
            const dr = drafts[r.id];
            // Name drafts for every animal box, including excluded ones (so
            // re-including a box gets its AIY guess back)
            (r.detections || []).filter(d => d.listed && d.category === 'animal').forEach(d => {
                if (!dr[d.id]) dr[d.id] = { name: (d.species_aiy && d.species_aiy !== 'background') ? aiyLabel(d) : '' };
            });
            return dr;
        }

        function quickButtons(sid, did) {
            return quickNames.map(([short, full]) =>
                `<button class="btn-mini" onclick="setName(${sid}, '${did}', '${escAttr(full).replace(/'/g, "\\'")}')">${esc(short)}</button>`).join('');
        }

        // Species Queue shows AIY's SPECIES % on the boxes; clicking a box
        // excludes it (or includes it again) - saved immediately.
        const boxOpts = { pct: 'aiy', onClick: d => toggleExclude(d.id) };

        function renderLightbox() {
            if (lightboxIndex < 0 || lightboxIndex >= view.length) { closeLightbox(); return; }
            const r = view[lightboxIndex];
            const img = document.getElementById('lbImg');
            img.src = `/images/${r.filename}`;
            drawBoxes(img, r, boxOpts);
            const draft = draftFor(r);
            const listed = listedBoxes(r);
            let panel = `<div class="lb-date">${r.date} &middot; ${detectorBadge(r)} (${lightboxIndex + 1} of ${view.length})
                <span class="bx-toggle" onclick="toggleBoxes(document.getElementById('lbImg'), view[lightboxIndex], boxOpts)">&nbsp; show / hide boxes (b) &middot; click a box to exclude it</span></div>`;

            if (r.detect_status === 'pending') {
                panel += `<div class="waiting">Still scanning this photo for birds - you can name it now or wait.</div>`;
            }
            listed.forEach((d, i) => {
                const exBtn = `<button class="btn-mini ${d.excluded ? 'on' : ''}" onclick="toggleExclude(${d.id})"
                    title="Leaf, shadow, reflection, watering can...">${d.excluded ? 'Excluded - include' : 'Exclude'}</button>`;
                if (d.category !== 'animal') {
                    // People / vehicles: nothing to name, only exclude
                    panel += `<div class="bird-row">
                        <span class="bird-num" style="background:${d.excluded ? '#888' : '#ff9800'}">${i + 1}</span>
                        <span style="flex:1; ${d.excluded ? 'text-decoration:line-through; color:#aaa' : ''}">${esc(d.category)} (detector ${pctText(d.det_conf)})</span>
                        ${exBtn}</div>`;
                    return;
                }
                const dr = draft[d.id];
                const conf = d.confidence_aiy != null ? `AIY ${pctText(d.confidence_aiy)}` : 'AIY -';
                panel += `<div class="bird-row">
                    <span class="bird-num" style="${d.excluded ? 'background:#888' : ''}">${i + 1}</span>
                    ${nameBox(r.id, d.id, dr.name, 'Name this bird...', d.excluded)}
                    <span class="aiy-conf">${conf}</span>
                    ${d.excluded ? '' : quickButtons(r.id, d.id)}
                    ${exBtn}
                </div>`;
            });
            if (!birdsOf(r).length) {
                // No bird left to name - one name for the whole photo
                panel += `<div class="bird-row">
                    ${nameBox(r.id, 'photo', draft.photo.name, 'No bird found - name it anyway...', false)}
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

        // ---------- name picker ----------
        // Type part of a common or Latin name (any order: "fin hou" finds
        // House Finch); the arrow shows the full list. Up/Down + Enter or
        // Tab picks, Esc closes, Ctrl+Enter posts.
        const allNames = __NAMES_JSON__;
        let nmActive = null, nmHi = -1, nmShown = [];
        function nameBox(sid, did, value, placeholder, disabled) {
            const id = did === 'photo' ? 'name-photo' : `name-${did}`;
            return `<div class="nm-wrap">
                <input id="${id}" value="${escAttr(value)}" placeholder="${placeholder}" autocomplete="off" ${disabled ? 'disabled' : ''}
                       data-sid="${sid}" data-did="${did}" oninput="nmInput(this)" onkeydown="nmKey(event, this)" onblur="nmClose()">
                ${disabled ? '' : `<button class="nm-arrow" tabindex="-1" onmousedown="event.preventDefault()" onclick="nmToggle(this)">&#9662;</button>`}
                <div class="nm-list"></div></div>`;
        }
        function nmSave(input) {
            const sid = +input.dataset.sid, did = input.dataset.did;
            if (did === 'photo') drafts[sid].photo.name = input.value;
            else drafts[sid][did].name = input.value;
        }
        function nmMatches(q) {
            const words = q.toLowerCase().split(/\s+/).filter(Boolean);
            if (!words.length) return allNames;
            const hits = allNames.filter(n => { const l = n.toLowerCase(); return words.every(w => l.includes(w)); });
            // Best first: names where each typed word starts a word ("fin hou"
            // -> House Finch before Cassin's Finch), then alphabetical.
            const score = n => words.filter(w => new RegExp('(^|[\\s(\'-])' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(n.toLowerCase())).length;
            return hits.map(n => [score(n), n]).sort((a, b) => b[0] - a[0] || a[1].localeCompare(b[1])).map(x => x[1]);
        }
        function nmOpen(input, names) {
            nmActive = input; nmShown = names;
            nmHi = Math.max(0, nmShown.indexOf(input.value));
            if (!nmShown.length) nmHi = -1;
            const list = input.parentElement.querySelector('.nm-list');
            list.innerHTML = nmShown.length
                ? nmShown.map((n, i) => `<div class="nm-opt${i === nmHi ? ' hi' : ''}" onmousedown="event.preventDefault(); nmPick(${i})">${esc(n)}</div>`).join('')
                : '<div class="nm-none">No match - post it as typed, or keep typing</div>';
            list.classList.add('open');
            const hi = list.querySelector('.hi'); if (hi) hi.scrollIntoView({ block: 'nearest' });
        }
        function nmClose() {
            document.querySelectorAll('.nm-list.open').forEach(l => l.classList.remove('open'));
            nmActive = null; nmHi = -1;
        }
        function nmInput(input) { nmSave(input); nmOpen(input, nmMatches(input.value)); nmHi = nmShown.length ? 0 : -1; nmMark(); }
        function nmToggle(btn) {
            const input = btn.parentElement.querySelector('input');
            if (nmActive === input) { nmClose(); return; }
            input.focus();
            nmOpen(input, allNames);   // the arrow always shows every name
        }
        function nmMark() {
            if (!nmActive) return;
            const opts = nmActive.parentElement.querySelectorAll('.nm-opt');
            opts.forEach((o, i) => o.classList.toggle('hi', i === nmHi));
            if (opts[nmHi]) opts[nmHi].scrollIntoView({ block: 'nearest' });
        }
        function nmPick(i) {
            if (!nmActive || !nmShown[i]) return;
            const input = nmActive;
            input.value = nmShown[i];
            nmSave(input);
            nmClose();
        }
        function nmKey(e, input) {
            const open = nmActive === input;
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (!open) { nmOpen(input, nmMatches(input.value)); return; }
                nmHi = Math.min(nmShown.length - 1, Math.max(0, nmHi + (e.key === 'ArrowDown' ? 1 : -1)));
                nmMark();
            } else if ((e.key === 'Enter' && !e.ctrlKey) || e.key === 'Tab') {
                if (open && nmHi >= 0) { e.preventDefault(); nmPick(nmHi); }
                else if (e.key === 'Enter') e.preventDefault();
            } else if (e.key === 'Escape' && open) {
                e.preventDefault(); e.stopPropagation(); nmClose();
            }
        }

        function setName(sid, did, name) {
            const dr = drafts[sid];
            if (did === 'photo') dr.photo.name = name;
            else dr[did].name = name;
            renderLightbox();
        }

        async function toggleExclude(detectionId) {
            const r = view[lightboxIndex];
            if (!r) return;
            const d = (r.detections || []).find(x => x.id === detectionId);
            if (!d) return;
            if (!(await setExcluded(r, d, !d.excluded))) { showInfo('Could not save that - try again.'); return; }
            renderLightbox();
            renderGrid();
        }

        async function postCurrent() {
            const r = view[lightboxIndex];
            if (!r) return;
            const draft = draftFor(r);
            const birds = birdsOf(r);   // excluded boxes are already left out
            const body = {};
            if (birds.length) {
                body.birds = birds.map(d => {
                    const name = (draft[d.id].name || '').trim();
                    return name ? { detection_id: d.id, species_confirmed: name, source: name === aiyLabel(d) ? 'aiy' : 'custom' } : null;
                });
                if (body.birds.some(b => b === null)) { showInfo('Every bird needs a name (or Exclude it).'); return; }
                // Photo-level name (family page, older views): the first bird
                body.species_confirmed = body.birds[0].species_confirmed;
                body.species_confirmed_source = body.birds[0].source;
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
            showInfo(`Posted to Gallery: ${body.birds ? body.birds.map(b => b.species_confirmed).join(', ') : body.species_confirmed}`);
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
        // Resend no longer leaves the queue (2026-10-25): the photo stays here,
        // shown as "still scanning" until the detector finishes (~10-20 s;
        // reload the page to see the new boxes).
        function markRescanning(id) {
            const r = byId(id);
            if (r) { r.detect_status = 'pending'; r.species_id_status = 'queued'; }
        }
        async function resendToClassifier(id) {
            const res = await fetch(`/api/sightings/${id}/resend-classifier`, { method: 'POST' });
            if (!res.ok) { showInfo('Could not resend - try again.'); return; }
            markRescanning(id);
            showInfo('Re-scanning for birds - reload in a minute to see the new boxes');
            applyView();
            if (lightboxIndex >= 0) renderLightbox();
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
            else if (e.key === 'b' && lightboxIndex >= 0) toggleBoxes(document.getElementById('lbImg'), view[lightboxIndex], boxOpts);
        });

        applyView();
    </script>
</body>
</html>
"""


@router.get("/species-queue")
async def species_queue_page():
    """Name the birds in every new photo (since 2026-10-25 photos arrive here
    straight from the camera - there's no Manage screen first). Every
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
        "species_id_status, detect_status, animal_count, person_count, max_det_conf, count_threshold "
        "FROM sightings WHERE species_id_status IN ('queued', 'classified') "
        "AND review_status = 'pending_review' "
        "ORDER BY timestamp DESC LIMIT ?", (QUEUE_LIMIT,)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    total = cursor.execute("SELECT COUNT(*) FROM sightings WHERE species_id_status IN ('queued', 'classified') "
                           "AND review_status = 'pending_review'").fetchone()[0]
    _attach_detections(cursor, rows)
    conn.close()

    for r in rows:
        r["aiy_label"] = r["common_name"] or r["species_aiy"] or "Unknown"
        r["date"] = r["timestamp"].split("T")[0]

    names = sorted({f"{c} ({s})" for s, c in common_names.items() if c and s != "background"} | set(EXTRA_NAMES),
                   key=str.lower)

    html = (PAGE.replace("__BOXES_CSS__", BOXES_CSS).replace("__DBADGE_CSS__", DBADGE_CSS)
                .replace("__BOXES_JS__", BOXES_JS)
                .replace("__NAV__", NAV_HTML)
                .replace("__NAMES_JSON__", json_module.dumps(names).replace("<", "\\u003c"))
                .replace("__QUICK_NAMES__", json_module.dumps(QUICK_NAMES))
                .replace("__QUEUE_TOTAL__", str(total))
                .replace("__QUEUE_DATA__", json_module.dumps(rows).replace("<", "\\u003c")))
    return HTMLResponse(html)
