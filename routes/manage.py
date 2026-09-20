from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()

@router.get("/manage")
async def manage_page():
    """Bulk review of pending_review sightings. Filter, batch Accept/Resend/Delete,
    or open a single sighting in the preview modal for one-at-a-time triage with
    next/prev navigation and inline Approve/Resend/Reject actions."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage - Review Sightings</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
            .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
            h1 { margin-bottom: 20px; font-size: 24px; }
            .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; padding: 15px; background: #fafafa; border-radius: 6px; }
            .filter-group { display: flex; flex-direction: column; }
            .filter-group label { font-size: 12px; font-weight: 600; color: #666; margin-bottom: 5px; }
            input[type="date"], input[type="range"], select { padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
            .controls { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }
            button { padding: 10px 16px; border: none; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; }
            .btn-primary { background: #007bff; color: white; }
            .btn-primary:hover { background: #0056b3; }
            .btn-success { background: #28a745; color: white; }
            .btn-success:hover { background: #218838; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-danger:hover { background: #c82333; }
            .btn-secondary { background: #6c757d; color: white; }
            .btn-secondary:hover { background: #5a6268; }
            button:disabled { opacity: 0.5; cursor: not-allowed; }
            .pagination { display: flex; gap: 10px; align-items: center; }
            .table-wrapper { overflow-x: auto; margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th { background: #f8f9fa; padding: 12px; text-align: left; font-weight: 600; font-size: 13px; border-bottom: 2px solid #dee2e6; }
            td { padding: 12px; border-bottom: 1px solid #dee2e6; }
            tr:hover { background: #f9f9f9; }
            .thumb { width: 50px; height: 50px; object-fit: cover; cursor: pointer; border-radius: 4px; }
            .info { padding: 12px; background: #e7f3ff; border-left: 4px solid #007bff; margin-bottom: 15px; font-size: 13px; display: none; }
            .busy-overlay { display: none; position: fixed; z-index: 1001; left: 0; top: 0; width: 100%; height: 100%; background: rgba(255,255,255,0.85); align-items: center; justify-content: center; flex-direction: column; }
            .busy-overlay.active { display: flex; }
            .spinner { width: 44px; height: 44px; border: 5px solid #dee2e6; border-top-color: #007bff; border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 16px; }
            @keyframes spin { to { transform: rotate(360deg); } }
            .busy-msg { font-weight: 600; color: #333; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Manage - Review Sightings</h1>
            __NAV__
            <div class="info" id="info"></div>

            <div class="filters">
                <div class="filter-group"><label>Date From</label><input type="date" id="dateFrom"></div>
                <div class="filter-group"><label>Date To</label><input type="date" id="dateTo"></div>
                <div class="filter-group"><label>Species</label><select id="species"><option value="">All Species</option></select></div>
                <div class="filter-group"><label>Max Confidence: <span id="confLabel">100%</span></label><input type="range" id="confidence" min="0" max="100" value="100"></div>
            </div>

            <div class="controls">
                <button class="btn-primary" onclick="applyFilters()">Apply Filters</button>
                <button class="btn-secondary" onclick="clearFilters()">Clear</button>
                <button class="btn-primary" onclick="autoPopulateDates()" style="margin-left: 10px;">Auto-populate Dates</button>
                <span id="selectedCount" style="margin-left: auto; color: #666;"></span>
            </div>

            <div class="controls">
                <button class="btn-success" onclick="acceptSelected()" id="btnAccept" disabled>Send to Species Queue</button>
                <button class="btn-primary" onclick="resendSelected()" id="btnResend" disabled>Resend to Classifier</button>
                <button class="btn-danger" onclick="deleteSelected()" id="btnDel" disabled>Reject to Trash</button>
            </div>

            <div class="controls pagination">
                <label>Per page:</label>
                <select id="perPage" onchange="applyFilters()">
                    <option value="10">10</option>
                    <option value="25" selected>25</option>
                    <option value="50">50</option>
                    <option value="100">100</option>
                </select>
                <span id="pageInfo" style="margin-left: auto;"></span>
            </div>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th style="width:40px;"><input type="checkbox" id="selectAll" onchange="toggleSelectAll()"></th>
                            <th style="width:60px;">Image</th>
                            <th>Common Name</th>
                            <th>Species (Latin)</th>
                            <th style="width:90px;">SpeciesNet</th>
                            <th style="width:70px;">Attempts</th>
                            <th style="width:90px;">Confidence</th>
                            <th style="width:140px;">Date</th>
                        </tr>
                    </thead>
                    <tbody id="tbody"><tr><td colspan="8" style="text-align:center; padding:40px; color:#999;">Loading...</td></tr></tbody>
                </table>
            </div>
        </div>

        <div class="lightbox" id="previewModal" style="display:none; position:fixed; z-index:999; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.9); align-items:center; justify-content:center; flex-direction:column;">
            <span onclick="closePreview()" style="position:absolute; top:20px; right:30px; color:white; font-size:28px; cursor:pointer; user-select:none;">&times;</span>
            <button onclick="navPreview(-1)" style="position:absolute; left:20px; top:50%; transform:translateY(-50%); font-size:28px; padding:14px 18px; background:rgba(255,255,255,0.15); color:white;">&#8592;</button>
            <button onclick="navPreview(1)" style="position:absolute; right:20px; top:50%; transform:translateY(-50%); font-size:28px; padding:14px 18px; background:rgba(255,255,255,0.15); color:white;">&#8594;</button>
            <img id="previewImg" style="max-width:80%; max-height:65%; border-radius:4px;">
            <div style="color:white; margin-top:15px; text-align:center;">
                <div id="previewCommon" style="font-size:20px; font-weight:600;"></div>
                <div id="previewMeta" style="font-size:13px; color:#ccc; margin-top:4px;"></div>
            </div>
            <div class="controls" style="margin-top:18px;">
                <button class="btn-success" onclick="previewAction('approve')">Send to Species Queue</button>
                <button class="btn-primary" onclick="previewAction('resend')">Resend to Classifier</button>
                <button class="btn-danger" onclick="previewAction('reject')">Reject to Trash</button>
            </div>
        </div>

        <div class="busy-overlay" id="busyOverlay">
            <div class="spinner"></div>
            <div class="busy-msg" id="busyMsg">Working...</div>
        </div>

        <script>
            let currentPage = 1, allSightings = [], selectedIds = new Set(), previewIndex = -1;
            let speciesLabels = {};

            async function loadSpecies() {
                const res = await fetch('/api/species-list?review_status=pending_review');
                const data = await res.json();
                const sel = document.getElementById('species');
                data.species.forEach(sp => {
                    speciesLabels[sp.value] = sp.label;
                    const opt = document.createElement('option');
                    opt.value = sp.value;
                    opt.textContent = sp.label;
                    sel.appendChild(opt);
                });
            }
            async function autoPopulateDates() {
                const res = await fetch('/api/sightings?review_status=pending_review&species_id_status=not_queued&limit=1');
                const data = await res.json();
                if (data.items.length === 0) { alert('No pending reviews'); return; }
                const dates = data.items.map(s => s.timestamp.split('T')[0]);
                document.getElementById('dateFrom').value = Math.min(...dates);
                document.getElementById('dateTo').value = Math.max(...dates);
                applyFilters();
            }

            async function applyFilters() {
                currentPage = 1;
                selectedIds.clear();
                document.getElementById('selectAll').checked = false;
                updateSelectedCount();
                await loadSightings();
            }

            async function loadSightings() {
                const dateFrom = document.getElementById('dateFrom').value;
                const dateTo = document.getElementById('dateTo').value;
                const species = document.getElementById('species').value;
                const conf = parseInt(document.getElementById('confidence').value) / 100;
                const perPage = parseInt(document.getElementById('perPage').value);

                const params = new URLSearchParams({
                    confidence_min: 0,
                    confidence_max: conf,
                    page: currentPage,
                    limit: perPage,
                    review_status: 'pending_review',
                    species_id_status: 'not_queued'
                });
                if (dateFrom) params.append('date_from', dateFrom);
                if (dateTo) params.append('date_to', dateTo);
                if (species) params.append('species', species);

                const res = await fetch(`/api/sightings?${params}`);
                const data = await res.json();
                allSightings = data.items;

                const tbody = document.getElementById('tbody');
                tbody.innerHTML = '';
                if (allSightings.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:40px; color:#999;">No sightings found</td></tr>';
                    document.getElementById('pageInfo').textContent = 'No results';
                    return;
                }

                allSightings.forEach((s, idx) => {
                    const tr = document.createElement('tr');
                    const common = s.common_name || speciesLabels[s.species_aiy] || s.species_aiy || 'Unknown';
                    tr.innerHTML = `<td><input type="checkbox" value="${s.id}" onchange="updateSelectedCount()"></td><td><img src="/images/${s.filename}" class="thumb" onclick="openPreview(${idx})"></td><td>${common}</td><td>${s.species_aiy || 'Unknown'}</td><td>${speciesIdBadge(s.species_id_status)}</td><td>${s.classification_attempts || 1}</td><td>${(s.confidence_aiy * 100).toFixed(0)}%</td><td><small>${s.timestamp.split('T')[0]}</small></td>`;
                    tbody.appendChild(tr);
                });

                const totalPages = Math.ceil(data.total / perPage);
                document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages} (${data.total} total)`;
            }

            function toggleSelectAll() {
                const checked = document.getElementById('selectAll').checked;
                document.querySelectorAll('tbody input[type="checkbox"]').forEach(cb => cb.checked = checked);
                updateSelectedCount();
            }

            function updateSelectedCount() {
                selectedIds.clear();
                document.querySelectorAll('tbody input[type="checkbox"]:checked').forEach(cb => selectedIds.add(parseInt(cb.value)));
                document.getElementById('selectedCount').textContent = selectedIds.size + ' selected';
                ['btnAccept', 'btnResend', 'btnDel'].forEach(id => document.getElementById(id).disabled = selectedIds.size === 0);
            }
            function openPreview(idx) {
                previewIndex = idx;
                renderPreview();
                document.getElementById('previewModal').style.display = 'flex';
            }

            function closePreview() {
                document.getElementById('previewModal').style.display = 'none';
                previewIndex = -1;
            }

            function renderPreview() {
                if (previewIndex < 0 || previewIndex >= allSightings.length) { closePreview(); return; }
                const s = allSightings[previewIndex];
                const common = s.common_name || speciesLabels[s.species_aiy] || s.species_aiy || 'Unknown';
                document.getElementById('previewImg').src = `/images/${s.filename}`;
                document.getElementById('previewCommon').textContent = common;
                document.getElementById('previewMeta').textContent =
                    `${s.species_aiy || 'Unknown'} - ${(s.confidence_aiy * 100).toFixed(0)}% - attempt ${s.classification_attempts || 1} - SN: ${s.species_id_status || 'not_queued'} - ${s.timestamp.split('T')[0]} (${previewIndex + 1} of ${allSightings.length})`;
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
                    // Queues for species ID - does NOT change review_status,
                    // so this stays 'pending_review' server-side. Splicing
                    // it out here just hides it for the rest of THIS working
                    // session; a fresh page load will show it again, which
                    // is correct given review_status and species_id_status
                    // are deliberately independent fields.
                    const res = await fetch(`/api/sightings/${s.id}/queue-species-id`, { method: 'POST' });
                    const data = await res.json();
                    if (data.already_in_pipeline) {
                        showInfo(`Already in the pipeline (${data.species_id_status}) - nothing changed`);
                    } else {
                        allSightings.splice(previewIndex, 1);
                    }
                } else if (action === 'reject') {
                    await fetch(`/api/sightings/${s.id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'rejected'}) });
                    allSightings.splice(previewIndex, 1);
                } else if (action === 'resend') {
                    const res = await fetch(`/api/sightings/${s.id}/resend-classifier`, { method: 'POST' });
                    const updated = await res.json();
                    Object.assign(s, updated);
                }
                // Reflect the change in the underlying table without a full
                // reload, then move on - matches "advance to next image" for
                // every action, per the plan, not just the removing ones.
                loadSightingsTableOnly();
                if (previewIndex >= allSightings.length) previewIndex = allSightings.length - 1;
                renderPreview();
            }

            function loadSightingsTableOnly() {
                const tbody = document.getElementById('tbody');
                tbody.innerHTML = '';
                if (allSightings.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:40px; color:#999;">No sightings found</td></tr>';
                    return;
                }
                allSightings.forEach((s, idx) => {
                    const tr = document.createElement('tr');
                    const common = s.common_name || speciesLabels[s.species_aiy] || s.species_aiy || 'Unknown';
                    tr.innerHTML = `<td><input type="checkbox" value="${s.id}" onchange="updateSelectedCount()"></td><td><img src="/images/${s.filename}" class="thumb" onclick="openPreview(${idx})"></td><td>${common}</td><td>${s.species_aiy || 'Unknown'}</td><td>${speciesIdBadge(s.species_id_status)}</td><td>${s.classification_attempts || 1}</td><td>${(s.confidence_aiy * 100).toFixed(0)}%</td><td><small>${s.timestamp.split('T')[0]}</small></td>`;
                    tbody.appendChild(tr);
                });
            }

            document.addEventListener('keydown', e => {
                if (document.getElementById('previewModal').style.display !== 'flex') return;
                if (e.key === 'ArrowLeft') navPreview(-1);
                else if (e.key === 'ArrowRight') navPreview(1);
                else if (e.key === 'Escape') closePreview();
            });
            function clearFilters() {
                document.getElementById('dateFrom').value = '';
                document.getElementById('dateTo').value = '';
                document.getElementById('species').value = '';
                document.getElementById('confidence').value = 100;
                document.getElementById('confLabel').textContent = '100%';
                applyFilters();
            }

            async function acceptSelected() {
                if (!confirm(`Send ${selectedIds.size} to species queue?`)) return;
                const ids = Array.from(selectedIds);
                let newlyQueued = 0, alreadyInPipeline = 0;
                setBusy(true, `Sending 0 of ${ids.length}...`);
                for (let i = 0; i < ids.length; i++) {
                    const res = await fetch(`/api/sightings/${ids[i]}/queue-species-id`, { method: 'POST' });
                    const data = await res.json();
                    if (data.already_in_pipeline) alreadyInPipeline++; else newlyQueued++;
                    setBusy(true, `Sending ${i + 1} of ${ids.length}...`);
                }
                setBusy(false);
                showInfo(alreadyInPipeline > 0
                    ? `Queued ${newlyQueued}, ${alreadyInPipeline} already in the pipeline (skipped)`
                    : `Sent ${newlyQueued} to species queue`);
                selectedIds.clear();
                await applyFilters();
            }

            async function resendSelected() {
                if (!confirm(`Resend ${selectedIds.size} to classifier?`)) return;
                const ids = Array.from(selectedIds);
                setBusy(true, `Resending 0 of ${ids.length}...`);
                for (let i = 0; i < ids.length; i++) {
                    await fetch(`/api/sightings/${ids[i]}/resend-classifier`, { method: 'POST' });
                    setBusy(true, `Resending ${i + 1} of ${ids.length}...`);
                }
                setBusy(false);
                showInfo(`Sent ${ids.length} to classifier`);
                selectedIds.clear();
                await applyFilters();
            }

            async function deleteSelected() {
                if (!confirm(`Reject ${selectedIds.size} to trash?`)) return;
                const ids = Array.from(selectedIds);
                setBusy(true, `Rejecting 0 of ${ids.length}...`);
                for (let i = 0; i < ids.length; i++) {
                    await fetch(`/api/sightings/${ids[i]}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'rejected'}) });
                    setBusy(true, `Rejecting ${i + 1} of ${ids.length}...`);
                }
                setBusy(false);
                showInfo(`Rejected ${ids.length} to trash`);
                selectedIds.clear();
                await applyFilters();
            }

            function speciesIdBadge(status) {
                const styles = {
                    not_queued: ['#e2e3e5', '#383d41', 'Not queued'],
                    queued: ['#fff3cd', '#856404', 'Queued'],
                    classified: ['#cce5ff', '#004085', 'Ready to review'],
                    confirmed: ['#d4edda', '#155724', 'Confirmed'],
                };
                const [bg, fg, text] = styles[status] || styles.not_queued;
                return `<span style="display:inline-block; font-size:11px; font-weight:600; padding:2px 6px; border-radius:8px; background:${bg}; color:${fg};">${text}</span>`;
            }

            function showInfo(msg) {
                const info = document.getElementById('info');
                info.textContent = msg;
                info.style.display = 'block';
                setTimeout(() => info.style.display = 'none', 4000);
            }

            function setBusy(isBusy, msg) {
                const overlay = document.getElementById('busyOverlay');
                if (isBusy) {
                    document.getElementById('busyMsg').textContent = msg || 'Working...';
                    overlay.classList.add('active');
                    ['btnAccept', 'btnResend', 'btnDel'].forEach(id => document.getElementById(id).disabled = true);
                } else {
                    overlay.classList.remove('active');
                }
            }

            document.getElementById('confidence').addEventListener('input', e => document.getElementById('confLabel').textContent = e.target.value + '%');
            loadSpecies();
            autoPopulateDates();
        </script>
    </body>
    </html>
    """
    html = html.replace("__NAV__", NAV_HTML)
    return HTMLResponse(html)
