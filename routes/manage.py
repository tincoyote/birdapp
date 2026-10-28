from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML
from routes.boxes import BOXES_CSS, BOXES_JS, DBADGE_CSS

router = APIRouter()

# Plain template with __PLACEHOLDER__ substitution (same pattern as
# species_queue.py) - no f-string brace escaping in the JS.
#
# 2026-10-25: Manage is now a cleanup view over the GALLERY (posted photos),
# not a bird/no-bird screen in front of Species Queue - new photos go
# straight to Species Queue (see main.queue_for_review). Same tools as
# before (quick filters, paging, bulk "all N matching", one-at-a-time
# preview), but the slider is the SPECIES confidence (AIY on the least sure
# bird) instead of the detector's "is it a bird", plus a species filter.
# Actions: reject to Trash, or send back to Species Queue to rename.
# Counts stay live while working in the preview (2026-10-22).
PAGE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Manage Gallery</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
        h1 { margin-bottom: 20px; font-size: 24px; }
        .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 15px; margin-bottom: 14px; padding: 15px; background: #fafafa; border-radius: 6px; }
        .filter-group { display: flex; flex-direction: column; }
        .filter-group label { font-size: 12px; font-weight: 600; color: #666; margin-bottom: 5px; }
        .hint { font-size: 11px; color: #888; margin-top: 3px; }
        input[type="date"], select { padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
        .range-pair { display: flex; gap: 6px; align-items: center; }
        .range-pair input { width: 100%; }
        .controls { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }
        button { padding: 10px 16px; border: none; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-outline-danger { background: white; color: #dc3545; border: 2px solid #dc3545; }
        .btn-outline-success { background: white; color: #28a745; border: 2px solid #28a745; }
        .btn-secondary { background: #6c757d; color: white; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .table-wrapper { overflow-x: auto; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f8f9fa; padding: 10px 12px; text-align: left; font-weight: 600; font-size: 13px; border-bottom: 2px solid #dee2e6; }
        td { padding: 8px 12px; border-bottom: 1px solid #dee2e6; font-size: 14px; }
        tr:hover { background: #f9f9f9; }
        .thumb { width: 96px; height: 54px; object-fit: cover; cursor: pointer; border-radius: 4px; display: block; }
        .bar { height: 6px; background: #e9ecef; border-radius: 3px; width: 90px; margin-top: 4px; }
        .bar span { display: block; height: 6px; border-radius: 3px; background: #28a745; }
        .info { padding: 12px; background: #e7f3ff; border-left: 4px solid #007bff; margin-bottom: 15px; font-size: 13px; display: none; }
        .busy-overlay { display: none; position: fixed; z-index: 1001; left: 0; top: 0; width: 100%; height: 100%; background: rgba(255,255,255,0.85); align-items: center; justify-content: center; flex-direction: column; }
        .busy-overlay.active { display: flex; }
        .spinner { width: 44px; height: 44px; border: 5px solid #dee2e6; border-top-color: #007bff; border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 16px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .busy-msg { font-weight: 600; color: #333; }
        .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); align-items: center; justify-content: center; flex-direction: column; }
        .lightbox.active { display: flex; }
        .lb-nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 28px; padding: 14px 18px; background: rgba(255,255,255,0.15); color: white; }
        __BOXES_CSS__
        __DBADGE_CSS__
    </style>
</head>
<body>
    <div class="container">
        <h1>Manage Gallery</h1>
        __NAV__
        <div class="info" id="info"></div>
        <div class="hint" style="margin:-8px 0 14px; font-size:13px">Clean up posted photos: find likely mis-IDs by species confidence, then reject them or send them back to Species Queue to rename.</div>

        <div class="filters">
            <div class="filter-group"><label>Date From</label><input type="date" id="dateFrom" onchange="applyFilters()"></div>
            <div class="filter-group"><label>Date To</label><input type="date" id="dateTo" onchange="applyFilters()"></div>
            <div class="filter-group"><label>Species</label>
                <select id="species" onchange="applyFilters()"><option value="">All species</option></select>
            </div>
            <div class="filter-group"><label>Birds in photo</label>
                <select id="birds" onchange="applyFilters()">
                    <option value="">Any</option>
                    <option value="1">Exactly 1</option>
                    <option value="2">2 or more</option>
                    <option value="0">None found</option>
                </select>
            </div>
            <div class="filter-group"><label>Kept</label>
                <select id="kept" onchange="applyFilters()">
                    <option value="hide">Hide kept</option>
                    <option value="">Show all</option>
                    <option value="only">Kept only</option>
                </select>
            </div>
            <div class="filter-group"><label>Person</label>
                <select id="person" onchange="applyFilters()">
                    <option value="">Any</option>
                    <option value="yes">Person in photo</option>
                    <option value="no">No person</option>
                </select>
            </div>
            <div class="filter-group">
                <label>Species confidence: <span id="spLabel">0% - 100%</span></label>
                <div class="range-pair">
                    <input type="range" id="spMin" min="0" max="100" value="0" oninput="syncSp()" onchange="applyFilters()">
                    <input type="range" id="spMax" min="0" max="100" value="100" oninput="syncSp()" onchange="applyFilters()">
                </div>
                <div class="hint">AIY's confidence in the least sure bird - of the chosen species, if one is picked. Low = likely mis-ID.</div>
            </div>
            <div class="filter-group">
                <label>Bird confidence: <span id="detLabel">0% - 100%</span></label>
                <div class="range-pair">
                    <input type="range" id="detMin" min="0" max="100" value="0" oninput="syncSp()" onchange="applyFilters()">
                    <input type="range" id="detMax" min="0" max="100" value="100" oninput="syncSp()" onchange="applyFilters()">
                </div>
                <div class="hint">Detector's confidence there's a bird at all.</div>
            </div>
            <div class="filter-group"><label>Sort</label>
                <select id="sortBy" onchange="applyFilters()">
                    <option value="timestamp">Newest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="sp_conf_asc">Species confidence, low first</option>
                    <option value="sp_conf">Species confidence, high first</option>
                    <option value="det_conf_asc">Bird confidence, low first</option>
                    <option value="det_conf">Bird confidence, high first</option>
                </select>
            </div>
        </div>

        <div class="controls">
            <button class="btn-secondary" onclick="clearFilters()">Clear filters</button>
            <span id="selectedCount" style="margin-left: auto; color: #666;"></span>
        </div>

        <div class="controls">
            <button class="btn-primary" onclick="requeueSelected()" id="btnAccept" disabled>Send selected back to Species Queue</button>
            <button class="btn-danger" onclick="deleteSelected()" id="btnDel" disabled>Reject selected to Trash</button>
            <button class="btn-success" onclick="keepSelected()" id="btnKeep" disabled>Keep selected</button>
            <span style="flex:1"></span>
            <button class="btn-outline-success" onclick="bulk('queue')" id="btnAllQueue" disabled>Send all matching back to Species Queue</button>
            <button class="btn-outline-danger" onclick="bulk('reject')" id="btnAllReject" disabled>Reject all matching</button>
        </div>

        <div class="controls pagination">
            <label>Per page:</label>
            <select id="perPage" onchange="applyFilters()">
                <option value="25">25</option>
                <option value="50" selected>50</option>
                <option value="100">100</option>
                <option value="200">200</option>
            </select>
            <button class="btn-secondary" onclick="page(-1)" id="btnPrev">&#8592; Prev</button>
            <button class="btn-secondary" onclick="page(1)" id="btnNext">Next &#8594;</button>
            <span id="pageInfo" style="margin-left: auto;"></span>
        </div>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th style="width:40px;"><input type="checkbox" id="selectAll" onchange="toggleSelectAll()"></th>
                        <th style="width:110px;">Image</th>
                        <th>Species</th>
                        <th style="width:130px;">Species confidence</th>
                        <th style="width:150px;">Date</th>
                    </tr>
                </thead>
                <tbody id="tbody"><tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Loading...</td></tr></tbody>
            </table>
        </div>
    </div>

    <div class="lightbox" id="previewModal">
        <span onclick="exitPreview()" style="position:absolute; top:20px; right:30px; color:white; font-size:28px; cursor:pointer; user-select:none;">&times;</span>
        <button class="lb-nav" style="left:20px;" onclick="navPreview(-1)">&#8592;</button>
        <button class="lb-nav" style="right:20px;" onclick="navPreview(1)">&#8594;</button>
        <div class="bx-wrap"><img id="previewImg"></div>
        <div style="color:white; margin-top:15px; text-align:center;">
            <div id="previewBirds" style="font-size:15px; font-weight:600;"></div>
            <div id="previewMeta" style="font-size:13px; color:#ccc; margin-top:4px;"></div>
            <div class="bx-toggle" onclick="toggleBoxes(document.getElementById('previewImg'), allSightings[previewIndex], boxOpts)">show / hide boxes (b) &middot; click a box to exclude it (e.g. a swinging watering can) or include it again</div>
        </div>
        <div class="controls" style="margin-top:14px;">
            <button class="btn-primary" onclick="previewAction('approve')">Back to Species Queue (a)</button>
            <button class="btn-danger" onclick="previewAction('reject')">Reject to Trash (r)</button>
            <button class="btn-success" id="btnPreviewKeep" onclick="previewAction('keep')">Keep (k)</button>
        </div>
    </div>

    <div class="busy-overlay" id="busyOverlay">
        <div class="spinner"></div>
        <div class="busy-msg" id="busyMsg">Working...</div>
    </div>

    <script>
        __BOXES_JS__
        let currentPage = 1, total = 0, allSightings = [], selectedIds = new Set(), previewIndex = -1;
        const $ = id => document.getElementById(id);

        function pair(minId, maxId) {
            let a = +$(minId).value, b = +$(maxId).value;
            if (a > b) { [a, b] = [b, a]; }
            return [a, b];
        }
        const spRange = () => pair('spMin', 'spMax');
        function syncSp() {
            const [a, b] = spRange(), [c, d] = pair('detMin', 'detMax');
            $('spLabel').textContent = `${a}% - ${b}%`;
            $('detLabel').textContent = `${c}% - ${d}%`;
        }
        // Same rule as the server's filter: the least sure bird - only birds
        // of the chosen species when one is picked in the Species filter.
        function speciesConf(s) {
            const want = $('species').value;
            const birds = countedBirds(s).filter(d => !want || (d.species_confirmed || d.species_aiy) === want);
            const c = birds.map(d => d.confidence_aiy).filter(v => v != null);
            return c.length ? Math.min(...c) : s.confidence_aiy;
        }
        function photoName(s) { return birdSummary(s) || s.species_confirmed || s.common_name || s.species_aiy || 'Unknown'; }
        function esc(t) { const d = document.createElement('div'); d.textContent = t ?? ''; return d.innerHTML; }

        async function loadSpecies() {
            const res = await fetch('/api/species-list?review_status=approved');
            const data = await res.json();
            data.species.forEach(sp => {
                const o = document.createElement('option');
                o.value = sp.value; o.textContent = sp.label;
                $('species').appendChild(o);
            });
        }

        // Presets just set the underlying filters, so what you see in the
        // controls is always exactly what's being filtered.
        function filterParams() {
            const [a, b] = spRange();
            const f = { review_status: 'approved' };
            if ($('dateFrom').value) f.date_from = $('dateFrom').value;
            if ($('dateTo').value) f.date_to = $('dateTo').value;
            if ($('species').value) f.species = $('species').value;
            // The top value includes that whole percent: 0-92 means "under 93%".
            const top = v => v >= 100 ? 1 : (v + 0.999) / 100;
            if (a > 0 || b < 100) { f.sp_conf_min = a / 100; f.sp_conf_max = top(b); }
            const [c, d] = pair('detMin', 'detMax');
            if (c > 0 || d < 100) { f.det_conf_min = c / 100; f.det_conf_max = top(d); }
            const nb = $('birds').value;
            if (nb === '0') f.animal_max = 0;
            if (nb === '1') { f.animal_min = 1; f.animal_max = 1; }
            if (nb === '2') f.animal_min = 2;
            if ($('person').value === 'yes') f.has_person = true;
            if ($('person').value === 'no') f.no_person = true;
            if ($('kept').value) f.kept = $('kept').value;
            return f;
        }

        async function applyFilters() {
            currentPage = 1;
            await loadSightings();
        }
        function page(delta) {
            const pages = Math.max(1, Math.ceil(total / +$('perPage').value));
            currentPage = Math.min(pages, Math.max(1, currentPage + delta));
            loadSightings();
        }

        async function loadSightings() {
            selectedIds.clear();
            $('selectAll').checked = false;
            const perPage = +$('perPage').value;
            const params = new URLSearchParams({ ...filterParams(), page: currentPage, limit: perPage, sort_by: $('sortBy').value });
            const res = await fetch(`/api/sightings?${params}`);
            const data = await res.json();
            allSightings = data.items;
            total = data.total;
            // Handled photos leave the filter, so the last page can vanish:
            // step back to the new last page instead of showing an empty one.
            const lastPage = Math.max(1, Math.ceil(total / perPage));
            if (currentPage > lastPage) { currentPage = lastPage; return loadSightings(); }
            renderTable();
            renderCounts();
            updateSelectedCount();
        }

        // Everything that shows `total`. Called after a full load and after
        // each single-photo action in the preview, so the numbers never lag.
        function renderCounts() {
            const pages = Math.max(1, Math.ceil(total / +$('perPage').value));
            $('pageInfo').textContent = total ? `Page ${currentPage} of ${pages} (${total} matching)` : 'No results';
            $('btnPrev').disabled = currentPage <= 1;
            $('btnNext').disabled = currentPage >= pages;
            $('btnAllQueue').disabled = $('btnAllReject').disabled = total === 0;
            $('btnAllQueue').textContent = `Send all ${total} matching back to Species Queue`;
            $('btnAllReject').textContent = `Reject all ${total} matching`;
        }

        function renderTable() {
            const tbody = $('tbody');
            if (allSightings.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">No sightings found</td></tr>';
                return;
            }
            tbody.innerHTML = allSightings.map((s, idx) => {
                const sc = speciesConf(s);
                const pct = sc == null ? null : Math.floor(sc * 100);  // rounded down, so 92.5% sits in 'under 93'
                const bar = pct === null ? '<small style="color:#999">-</small>'
                    : `${pct}%<div class="bar"><span style="width:${pct}%; background:${pct >= 50 ? '#28a745' : pct >= 20 ? '#ffc107' : '#dc3545'}"></span></div>`;
                const people = (s.person_count || 0) > 0 ? ' <span class="dbadge" style="background:#ffe0b2;color:#8a4b00">person</span>' : '';
                return `<tr><td><input type="checkbox" value="${s.id}" onchange="updateSelectedCount()"></td>
                    <td><img src="/images/${s.filename}" class="thumb" loading="lazy" onclick="openPreview(${idx})"></td>
                    <td>${esc(photoName(s))}<br>${detectorBadge(s)}${people}${s.is_favorite ? ' <span class="dbadge" style="background:#cce5ff;color:#004085">kept</span>' : ''}</td>
                    <td>${bar}</td>
                    <td><small>${s.timestamp.replace('T', ' ').slice(0, 16)}</small></td></tr>`;
            }).join('');
        }

        function toggleSelectAll() {
            const checked = $('selectAll').checked;
            document.querySelectorAll('tbody input[type="checkbox"]').forEach(cb => cb.checked = checked);
            updateSelectedCount();
        }

        function updateSelectedCount() {
            selectedIds.clear();
            document.querySelectorAll('tbody input[type="checkbox"]:checked').forEach(cb => selectedIds.add(parseInt(cb.value)));
            $('selectedCount').textContent = selectedIds.size ? selectedIds.size + ' selected' : '';
            ['btnAccept', 'btnDel', 'btnKeep'].forEach(id => $(id).disabled = selectedIds.size === 0);
        }

        // ---------- lightbox ----------
        function openPreview(idx) { previewIndex = idx; renderPreview(); $('previewModal').classList.add('active'); }
        function closePreview() { $('previewModal').classList.remove('active'); previewIndex = -1; }
        // Leaving the preview (Escape, the x, or running out of photos on this
        // page) reloads, so photos handled in the preview drop off the table
        // and the next page's photos move up.
        function exitPreview() { closePreview(); loadSightings(); }
        function renderPreview() {
            if (previewIndex < 0 || previewIndex >= allSightings.length) { closePreview(); return; }
            const s = allSightings[previewIndex];
            const img = $('previewImg');
            img.src = `/images/${s.filename}`;
            drawBoxes(img, s, boxOpts);
            const sc = speciesConf(s);
            $('previewBirds').innerHTML = esc(photoName(s))
                + (sc != null ? ` &middot; species confidence ${Math.floor(sc * 100)}%` : '')
                + ((s.person_count || 0) > 0 ? ' &middot; person' : '');
            $('btnPreviewKeep').textContent = s.is_favorite ? 'Kept - undo (k)' : 'Keep (k)';
            if (s.is_favorite) $('previewBirds').innerHTML += ' &middot; <span style="color:#7fc1ff">kept</span>';
            $('previewMeta').textContent = `${s.timestamp.replace('T', ' ').slice(0, 16)}  (${previewIndex + 1} of ${allSightings.length} on this page)`;
        }
        // Boxes show AIY's species % (since 2026-10-25, like Gallery); a
        // click on a box excludes it / includes it again, saved immediately.
        const boxOpts = { pct: 'aiy', onClick: async d => {
            const s = allSightings[previewIndex];
            if (!s) return;
            if (!(await setExcluded(s, d, !d.excluded))) { showInfo('Could not save that - try again.'); return; }
            renderTable();
            renderPreview();
        } };

        function navPreview(delta) {
            if (allSightings.length === 0) return;
            previewIndex = (previewIndex + delta + allSightings.length) % allSightings.length;
            renderPreview();
        }

        async function previewAction(action) {
            if (previewIndex < 0) return;
            const s = allSightings[previewIndex];
            if (action === 'keep') {
                // Toggle. When kept photos are hidden, a newly kept one leaves
                // the list like a reject does; otherwise it just gets the badge.
                const kept = !s.is_favorite;
                const res = await fetch(`/api/sightings/${s.id}/keep`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({kept}) });
                if (!res.ok) { showInfo('Could not save that - try again.'); return; }
                s.is_favorite = kept ? 1 : 0;
                const leaves = (kept && $('kept').value === 'hide') || (!kept && $('kept').value === 'only');
                if (!leaves) { renderTable(); renderPreview(); return; }
            } else if (action === 'approve') {
                // Back to Species Queue to rename - leaves the Gallery until re-posted
                const res = await fetch(`/api/sightings/${s.id}/queue-species-id`, { method: 'POST' });
                if (!res.ok) { showInfo('Could not send it back - try again.'); return; }
            } else {
                await fetch(`/api/sightings/${s.id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'rejected'}) });
            }
            // Drop it from this page and stay on the same index (= next photo)
            allSightings.splice(previewIndex, 1);
            total -= 1;
            renderTable();
            renderCounts();
            if (allSightings.length === 0) { exitPreview(); return; }
            if (previewIndex >= allSightings.length) previewIndex = allSightings.length - 1;
            renderPreview();
        }

        document.addEventListener('keydown', e => {
            if (!$('previewModal').classList.contains('active')) return;
            if (e.key === 'ArrowLeft') navPreview(-1);
            else if (e.key === 'ArrowRight') navPreview(1);
            else if (e.key === 'Escape') exitPreview();
            else if (e.key === 'a') previewAction('approve');
            else if (e.key === 'r') previewAction('reject');
            else if (e.key === 'k') previewAction('keep');
            else if (e.key === 'b' && previewIndex >= 0) toggleBoxes($('previewImg'), allSightings[previewIndex], boxOpts);
        });

        function clearFilters() {
            ['dateFrom', 'dateTo', 'species', 'birds', 'person'].forEach(id => $(id).value = '');
            $('kept').value = 'hide';
            $('spMin').value = 0; $('spMax').value = 100; $('detMin').value = 0; $('detMax').value = 100;
            $('sortBy').value = 'timestamp';
            syncSp();
            applyFilters();
        }

        // ---------- batch actions ----------
        async function eachSelected(verb, fn) {
            const ids = Array.from(selectedIds);
            if (!confirm(`${verb}: ${ids.length} photo(s)?`)) return;
            setBusy(true, `${verb} 0 of ${ids.length}...`);
            for (let i = 0; i < ids.length; i++) {
                await fn(ids[i]);
                setBusy(true, `${verb} ${i + 1} of ${ids.length}...`);
            }
            setBusy(false);
            showInfo(`${verb}: ${ids.length} done`);
            await loadSightings();
        }
        function requeueSelected() {
            eachSelected('Send back to Species Queue', id => fetch(`/api/sightings/${id}/queue-species-id`, { method: 'POST' }));
        }
        function keepSelected() {
            eachSelected('Keep', id => fetch(`/api/sightings/${id}/keep`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({kept: true}) }));
        }
        function deleteSelected() {
            eachSelected('Reject to Trash', id => fetch(`/api/sightings/${id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'rejected'}) }));
        }

        async function bulk(action) {
            const verb = action === 'reject' ? 'Reject to Trash' : 'Send back to Species Queue';
            if (!confirm(`${verb}: ALL ${total} photos matching the current filter (every page, not just this one)?` +
                         (action === 'reject' ? '\n\nThey go to Trash, so this can still be undone from there.' : ''))) return;
            setBusy(true, `${verb}: ${total} photos...`);
            const res = await fetch('/api/sightings/bulk-action', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filters: filterParams(), action, expected: total })
            });
            const data = await res.json();
            setBusy(false);
            if (data.stale) showInfo(`Nothing changed - the list changed since it loaded (now ${data.matched} matching). Check it and try again.`);
            else showInfo(`${verb}: ${data.done} photos`);
            await loadSightings();
        }

        function showInfo(msg) {
            const info = $('info');
            info.textContent = msg;
            info.style.display = 'block';
            setTimeout(() => info.style.display = 'none', 6000);
        }
        function setBusy(isBusy, msg) {
            const overlay = $('busyOverlay');
            if (isBusy) { $('busyMsg').textContent = msg || 'Working...'; overlay.classList.add('active'); }
            else overlay.classList.remove('active');
        }

        syncSp();
        // Links from Stats open Manage pre-filtered:
        // ?species=...  ?birds=2  ?sp_min=80&sp_max=89  ?kept=only
        loadSpecies().then(() => {
            const q = new URLSearchParams(location.search);
            if (q.get('species')) $('species').value = q.get('species');
            if (q.get('birds')) $('birds').value = q.get('birds');
            if (q.get('kept')) $('kept').value = q.get('kept') === 'all' ? '' : q.get('kept');
            if (q.get('sp_min')) $('spMin').value = q.get('sp_min');
            if (q.get('sp_max')) $('spMax').value = q.get('sp_max');
            syncSp();
            return loadSightings();
        });
    </script>
</body>
</html>
"""


@router.get("/manage")
async def manage_page():
    """Cleanup view over the Gallery (posted photos). Filter by species,
    species confidence, bird count or person; reject or send back to
    Species Queue - one at a time in the preview, a selection, or every
    match across pages."""
    html = (PAGE.replace("__BOXES_CSS__", BOXES_CSS).replace("__DBADGE_CSS__", DBADGE_CSS)
                .replace("__BOXES_JS__", BOXES_JS).replace("__NAV__", NAV_HTML))
    return HTMLResponse(html)
