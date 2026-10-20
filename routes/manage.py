from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML
from routes.boxes import BOXES_CSS, BOXES_JS, DBADGE_CSS

router = APIRouter()

# Plain template with __PLACEHOLDER__ substitution (same pattern as
# species_queue.py) - no f-string brace escaping in the JS.
#
# 2026-10-20: Manage filters on MegaDetector's result instead of AIY's
# full-frame confidence (which was measured not to separate bird/no-bird -
# see AUTO_TRASH_CONFIDENCE_THRESHOLD in main.py). "Best detection" is the
# detector's confidence in the most likely animal in the photo; a photo with
# no detection at all counts as 0%. The "all N matching" buttons act on
# every photo the filter matches, across pages, via /api/sightings/bulk-action.
PAGE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Manage - Review Sightings</title>
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
        .presets button { padding: 6px 12px; font-size: 13px; background: #e9ecef; color: #333; }
        .presets button.on { background: #343a40; color: white; }
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
        <h1>Manage - Review Sightings</h1>
        __NAV__
        <div class="info" id="info"></div>

        <div class="controls presets" id="presets">
            <span style="font-size:13px; color:#666;">Quick filter:</span>
            <button data-p="all" class="on" onclick="preset('all')">All</button>
            <button data-p="nobird" onclick="preset('nobird')">No bird found</button>
            <button data-p="bird" onclick="preset('bird')">Has bird(s)</button>
            <button data-p="multi" onclick="preset('multi')">2+ birds</button>
            <button data-p="person" onclick="preset('person')">Person in photo</button>
            <button data-p="pending" onclick="preset('pending')">Not scanned yet</button>
        </div>

        <div class="filters">
            <div class="filter-group"><label>Date From</label><input type="date" id="dateFrom" onchange="applyFilters()"></div>
            <div class="filter-group"><label>Date To</label><input type="date" id="dateTo" onchange="applyFilters()"></div>
            <div class="filter-group">
                <label>Best detection: <span id="detLabel">0% - 100%</span></label>
                <div class="range-pair">
                    <input type="range" id="detMin" min="0" max="100" value="0" oninput="syncDet()" onchange="applyFilters()">
                    <input type="range" id="detMax" min="0" max="100" value="100" oninput="syncDet()" onchange="applyFilters()">
                </div>
                <div class="hint">Detector's confidence in its most likely animal. Below __THR__% isn't counted as a bird.</div>
            </div>
            <div class="filter-group"><label>Sort</label>
                <select id="sortBy" onchange="applyFilters()">
                    <option value="timestamp">Newest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="det_conf_asc">Best detection, low first</option>
                    <option value="det_conf">Best detection, high first</option>
                </select>
            </div>
        </div>

        <div class="controls">
            <button class="btn-secondary" onclick="clearFilters()">Clear filters</button>
            <span id="selectedCount" style="margin-left: auto; color: #666;"></span>
        </div>

        <div class="controls">
            <button class="btn-success" onclick="acceptSelected()" id="btnAccept" disabled>Send selected to Species Queue</button>
            <button class="btn-danger" onclick="deleteSelected()" id="btnDel" disabled>Reject selected to Trash</button>
            <span style="flex:1"></span>
            <button class="btn-outline-success" onclick="bulk('queue')" id="btnAllQueue" disabled>Send all matching to Species Queue</button>
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
                        <th>Birds</th>
                        <th style="width:130px;">Best detection</th>
                        <th style="width:150px;">Date</th>
                    </tr>
                </thead>
                <tbody id="tbody"><tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Loading...</td></tr></tbody>
            </table>
        </div>
    </div>

    <div class="lightbox" id="previewModal">
        <span onclick="closePreview()" style="position:absolute; top:20px; right:30px; color:white; font-size:28px; cursor:pointer; user-select:none;">&times;</span>
        <button class="lb-nav" style="left:20px;" onclick="navPreview(-1)">&#8592;</button>
        <button class="lb-nav" style="right:20px;" onclick="navPreview(1)">&#8594;</button>
        <div class="bx-wrap"><img id="previewImg"></div>
        <div style="color:white; margin-top:15px; text-align:center;">
            <div id="previewBirds" style="font-size:15px; font-weight:600;"></div>
            <div id="previewMeta" style="font-size:13px; color:#ccc; margin-top:4px;"></div>
            <div class="bx-toggle" onclick="toggleBoxes(document.getElementById('previewImg'), allSightings[previewIndex].detections)">show / hide boxes (b)</div>
        </div>
        <div class="controls" style="margin-top:14px;">
            <button class="btn-success" onclick="previewAction('approve')">Send to Species Queue (a)</button>
            <button class="btn-danger" onclick="previewAction('reject')">Reject to Trash (r)</button>
        </div>
    </div>

    <div class="busy-overlay" id="busyOverlay">
        <div class="spinner"></div>
        <div class="busy-msg" id="busyMsg">Working...</div>
    </div>

    <script>
        __BOXES_JS__
        let currentPage = 1, total = 0, allSightings = [], selectedIds = new Set(), previewIndex = -1;
        let activePreset = 'all';
        const THR = __THR__ / 100;
        const $ = id => document.getElementById(id);

        function syncDet() {
            let a = +$('detMin').value, b = +$('detMax').value;
            if (a > b) { [a, b] = [b, a]; }
            $('detLabel').textContent = `${a}% - ${b}%`;
        }

        // Presets just set the underlying filters, so what you see in the
        // controls is always exactly what's being filtered.
        function preset(p) {
            activePreset = p;
            document.querySelectorAll('#presets button').forEach(b => b.classList.toggle('on', b.dataset.p === p));
            $('detMin').value = 0; $('detMax').value = 100;
            // "No bird" sorts highest-detection first, so the borderline
            // photos most worth a second look come up top.
            if (p === 'nobird') $('sortBy').value = 'det_conf';
            syncDet();
            applyFilters();
        }

        function filterParams() {
            let a = +$('detMin').value, b = +$('detMax').value;
            if (a > b) { [a, b] = [b, a]; }
            const f = { review_status: 'pending_review', species_id_status: 'not_queued' };
            if ($('dateFrom').value) f.date_from = $('dateFrom').value;
            if ($('dateTo').value) f.date_to = $('dateTo').value;
            if (a > 0 || b < 100) { f.det_conf_min = a / 100; f.det_conf_max = b / 100; }
            if (activePreset === 'nobird') f.animal_max = 0;
            if (activePreset === 'bird') f.animal_min = 1;
            if (activePreset === 'multi') f.animal_min = 2;
            if (activePreset === 'person') f.has_person = true;
            if (activePreset === 'pending') f.detect_status = 'pending';
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
            renderTable();
            const pages = Math.max(1, Math.ceil(total / perPage));
            $('pageInfo').textContent = total ? `Page ${currentPage} of ${pages} (${total} matching)` : 'No results';
            $('btnPrev').disabled = currentPage <= 1;
            $('btnNext').disabled = currentPage >= pages;
            $('btnAllQueue').disabled = $('btnAllReject').disabled = total === 0;
            $('btnAllQueue').textContent = `Send all ${total} matching to Species Queue`;
            $('btnAllReject').textContent = `Reject all ${total} matching`;
            updateSelectedCount();
        }

        function renderTable() {
            const tbody = $('tbody');
            if (allSightings.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">No sightings found</td></tr>';
                return;
            }
            tbody.innerHTML = allSightings.map((s, idx) => {
                const best = s.detect_status === 'done' ? Math.round((s.max_det_conf || 0) * 100) : null;
                const bar = best === null ? '<small style="color:#999">-</small>'
                    : `${best}%<div class="bar"><span style="width:${best}%; background:${best >= THR * 100 ? '#28a745' : '#adb5bd'}"></span></div>`;
                const people = (s.person_count || 0) > 0 ? ' <span class="dbadge" style="background:#ffe0b2;color:#8a4b00">person</span>' : '';
                return `<tr><td><input type="checkbox" value="${s.id}" onchange="updateSelectedCount()"></td>
                    <td><img src="/images/${s.filename}" class="thumb" loading="lazy" onclick="openPreview(${idx})"></td>
                    <td>${detectorBadge(s)}${people}</td>
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
            ['btnAccept', 'btnDel'].forEach(id => $(id).disabled = selectedIds.size === 0);
        }

        // ---------- lightbox ----------
        function openPreview(idx) { previewIndex = idx; renderPreview(); $('previewModal').classList.add('active'); }
        function closePreview() { $('previewModal').classList.remove('active'); previewIndex = -1; }
        function renderPreview() {
            if (previewIndex < 0 || previewIndex >= allSightings.length) { closePreview(); return; }
            const s = allSightings[previewIndex];
            const img = $('previewImg');
            img.src = `/images/${s.filename}`;
            drawBoxes(img, s.detections);
            const n = countedBirds(s).length;
            $('previewBirds').innerHTML = s.detect_status === 'pending' ? 'Not scanned yet'
                : (n ? `${n} bird${n > 1 ? 's' : ''} found` : 'No bird found')
                  + ((s.person_count || 0) > 0 ? ' &middot; person' : '');
            $('previewMeta').textContent = `${s.timestamp.replace('T', ' ').slice(0, 16)}  (${previewIndex + 1} of ${allSightings.length} on this page)`;
        }
        function navPreview(delta) {
            if (allSightings.length === 0) return;
            previewIndex = (previewIndex + delta + allSightings.length) % allSightings.length;
            renderPreview();
        }

        async function previewAction(action) {
            if (previewIndex < 0) return;
            const s = allSightings[previewIndex];
            if (action === 'approve') {
                const res = await fetch(`/api/sightings/${s.id}/queue-species-id`, { method: 'POST' });
                const data = await res.json();
                if (data.already_in_pipeline) { showInfo(`Already in the pipeline (${data.species_id_status})`); return; }
            } else {
                await fetch(`/api/sightings/${s.id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'rejected'}) });
            }
            // Drop it from this page and stay on the same index (= next photo)
            allSightings.splice(previewIndex, 1);
            total -= 1;
            renderTable();
            if (previewIndex >= allSightings.length) previewIndex = allSightings.length - 1;
            renderPreview();
        }

        document.addEventListener('keydown', e => {
            if (!$('previewModal').classList.contains('active')) return;
            if (e.key === 'ArrowLeft') navPreview(-1);
            else if (e.key === 'ArrowRight') navPreview(1);
            else if (e.key === 'Escape') { closePreview(); loadSightings(); }
            else if (e.key === 'a') previewAction('approve');
            else if (e.key === 'r') previewAction('reject');
            else if (e.key === 'b' && previewIndex >= 0) toggleBoxes($('previewImg'), allSightings[previewIndex].detections);
        });

        function clearFilters() {
            $('dateFrom').value = ''; $('dateTo').value = '';
            $('sortBy').value = 'timestamp';
            preset('all');
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
        function acceptSelected() {
            eachSelected('Send to Species Queue', id => fetch(`/api/sightings/${id}/queue-species-id`, { method: 'POST' }));
        }
        function deleteSelected() {
            eachSelected('Reject to Trash', id => fetch(`/api/sightings/${id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'rejected'}) }));
        }

        async function bulk(action) {
            const verb = action === 'reject' ? 'Reject to Trash' : 'Send to Species Queue';
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

        syncDet();
        loadSightings();
    </script>
</body>
</html>
"""


@router.get("/manage")
async def manage_page():
    """Bird / no-bird screening of fresh arrivals (pending_review, not yet
    queued). Filter by what MegaDetector found, batch-reject or batch-queue
    every match, or step through one photo at a time with boxes drawn on."""
    from main import DETECTOR_CONFIG
    thr = round(DETECTOR_CONFIG["count_threshold"] * 100)
    html = (PAGE.replace("__BOXES_CSS__", BOXES_CSS).replace("__DBADGE_CSS__", DBADGE_CSS)
                .replace("__BOXES_JS__", BOXES_JS).replace("__NAV__", NAV_HTML)
                .replace("__THR__", str(thr)))
    return HTMLResponse(html)
