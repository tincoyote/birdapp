from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML
from routes.boxes import BOXES_CSS, BOXES_JS, DBADGE_CSS

router = APIRouter()

@router.get("/trash")
async def trash_page():
    """Trash: rejected sightings. Filter by date, sort by most-recently-rejected
    first (so a just-made mistake is easy to find and restore quickly)."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Trash - Rejected Sightings</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
            .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
            h1 { margin-bottom: 20px; font-size: 24px; color: #dc3545; }
            .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; padding: 15px; background: #fafafa; border-radius: 6px; }
            .filter-group { display: flex; flex-direction: column; }
            .filter-group label { font-size: 12px; font-weight: 600; color: #666; margin-bottom: 5px; }
            input[type="date"], select { padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
            .table-wrapper { overflow-x: auto; margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th { background: #f8f9fa; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #dee2e6; }
            td { padding: 12px; border-bottom: 1px solid #dee2e6; }
            .thumb { width: 96px; height: 54px; object-fit: cover; border-radius: 4px; cursor: pointer; display: block; }
            .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.92); align-items: center; justify-content: center; flex-direction: column; }
            .lightbox.active { display: flex; }
            .lb-nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 28px; padding: 14px 18px; background: rgba(255,255,255,0.15); color: white; }
            __BOXES_CSS__
            .bx-wrap { max-width: 90%; }
            .lightbox .bx-wrap img { max-width: 100%; max-height: 70vh; }
            __DBADGE_CSS__
            button { padding: 10px 16px; border: none; border-radius: 4px; font-weight: 600; cursor: pointer; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-danger:hover { background: #c82333; }
            .btn-warning { background: #ffc107; color: black; }
            .btn-warning:hover { background: #e0a800; }
            .btn-primary { background: #007bff; color: white; }
            .btn-primary:hover { background: #0056b3; }
            .btn-secondary { background: #6c757d; color: white; }
            .btn-secondary:hover { background: #5a6268; }
            .controls { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
            .info { padding: 12px; background: #f8d7da; border-left: 4px solid #dc3545; margin-bottom: 15px; font-size: 13px; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Trash - Review Before Delete</h1>
            __NAV__
            <div class="info" id="info"></div>
            
            <div class="filters">
                <div class="filter-group"><label>Date From</label><input type="date" id="dateFrom"></div>
                <div class="filter-group"><label>Date To</label><input type="date" id="dateTo"></div>
                <div class="filter-group"><label>Species</label><select id="species"><option value="">All Species</option></select></div>
            </div>
            
            <div class="controls">
                <button class="btn-primary" onclick="applyFilters()">Apply Filters</button>
                <button class="btn-secondary" onclick="clearFilters()">Clear</button>
            </div>
            
            <div class="controls">
                <button class="btn-warning" onclick="restoreAll()">Restore All Visible</button>
                <button class="btn-danger" onclick="emptyTrash()">Permanently Delete All</button>
            </div>
            
            <div id="trashCount" style="margin-bottom: 15px; color: #666;"></div>
            
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th style="width:60px;">Image</th>
                            <th>Species</th>
                            <th style="width:90px;">Confidence</th>
                            <th style="width:140px;">Rejected</th>
                            <th style="width:100px;">Action</th>
                        </tr>
                    </thead>
                    <tbody id="tbody"><tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Loading...</td></tr></tbody>
                </table>
            </div>
        </div>
        
        <div class="lightbox" id="lightbox">
            <span onclick="closeLightbox()" style="position:absolute; top:20px; right:30px; color:white; font-size:28px; cursor:pointer; user-select:none;">&times;</span>
            <button class="lb-nav" style="left:20px;" onclick="navLightbox(-1)">&#8592;</button>
            <button class="lb-nav" style="right:20px;" onclick="navLightbox(1)">&#8594;</button>
            <div class="bx-wrap"><img id="lbImg"></div>
            <div style="color:white; margin-top:14px; text-align:center;">
                <div id="lbName" style="font-size:18px; font-weight:600;"></div>
                <div id="lbMeta" style="font-size:13px; color:#ccc; margin-top:4px;"></div>
                <div class="bx-toggle" onclick="toggleBoxes(document.getElementById('lbImg'), rows[lbIndex], {pct: 'aiy'})">show / hide boxes (b)</div>
            </div>
            <div class="controls" style="margin-top:14px;">
                <button class="btn-warning" onclick="restoreCurrent()">Restore (r)</button>
            </div>
        </div>

        <script>
            __BOXES_JS__
            let speciesLabels = {};
            let rows = [], lbIndex = -1;

            async function loadSpecies() {
                const res = await fetch('/api/species-list?review_status=rejected');
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

            function commonName(s) {
                return s.common_name || speciesLabels[s.species_aiy] || s.species_aiy || 'Unknown';
            }
            
            async function applyFilters() {
                const dateFrom = document.getElementById('dateFrom').value;
                const dateTo = document.getElementById('dateTo').value;
                const species = document.getElementById('species').value;
                
                const params = new URLSearchParams({ review_status: 'rejected', sort_by: 'review_updated_at', limit: 100 });
                if (dateFrom) params.append('date_from', dateFrom);
                if (dateTo) params.append('date_to', dateTo);
                if (species) params.append('species', species);
                
                const res = await fetch(`/api/sightings?${params}`);
                const data = await res.json();
                
                const tbody = document.getElementById('tbody');
                tbody.innerHTML = '';
                rows = data.items;
                if (data.items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Nothing here</td></tr>';
                    document.getElementById('trashCount').textContent = '';
                    return;
                }
                
                rows = data.items;
                data.items.forEach((s, idx) => {
                    const tr = document.createElement('tr');
                    const rejectedDate = (s.review_updated_at || s.timestamp || '').split('T')[0];
                    tr.innerHTML = `<td><img src="/images/${s.filename}" class="thumb" loading="lazy" onclick="openLightbox(${idx})" title="Click to view"></td><td>${commonName(s)}</td><td>${(s.confidence_aiy * 100).toFixed(0)}%</td><td><small>${rejectedDate}</small></td><td><button class="btn-warning" onclick="restoreItem(${s.id})">Restore</button></td>`;
                    tbody.appendChild(tr);
                });
                
                document.getElementById('trashCount').textContent = `${data.total} items in trash (most recently rejected first)`;
            }
            
            function clearFilters() {
                document.getElementById('dateFrom').value = '';
                document.getElementById('dateTo').value = '';
                document.getElementById('species').value = '';
                applyFilters();
            }
            
            // ---------- viewer (2026-10-20): check a photo before restoring ----------
            function photoName(s) { return birdSummary(s) || commonName(s); }
            function openLightbox(idx) { lbIndex = idx; renderLightbox(); document.getElementById('lightbox').classList.add('active'); }
            function closeLightbox() { document.getElementById('lightbox').classList.remove('active'); lbIndex = -1; }
            function navLightbox(delta) {
                if (!rows.length) return;
                lbIndex = (lbIndex + delta + rows.length) % rows.length;
                renderLightbox();
            }
            function renderLightbox() {
                if (lbIndex < 0 || lbIndex >= rows.length) { closeLightbox(); return; }
                const s = rows[lbIndex];
                const img = document.getElementById('lbImg');
                img.src = `/images/${s.filename}`;
                drawBoxes(img, s, { pct: 'aiy' });
                document.getElementById('lbName').textContent = photoName(s);
                const rej = (s.review_updated_at || '').replace('T', ' ').slice(0, 16);
                document.getElementById('lbMeta').innerHTML =
                    `${detectorBadge(s)} &nbsp;taken ${s.timestamp.replace('T', ' ').slice(0, 16)} &middot; rejected ${rej} (${lbIndex + 1} of ${rows.length})`;
            }
            async function restoreCurrent() {
                if (lbIndex < 0) return;
                const s = rows[lbIndex];
                await fetch(`/api/sightings/${s.id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                showInfo('Restored to review');
                rows.splice(lbIndex, 1);
                if (lbIndex >= rows.length) lbIndex = rows.length - 1;
                renderLightbox();
                applyFilters().then(() => { if (lbIndex >= 0) renderLightbox(); });
            }
            document.addEventListener('keydown', e => {
                if (!document.getElementById('lightbox').classList.contains('active')) return;
                if (e.key === 'ArrowLeft') navLightbox(-1);
                else if (e.key === 'ArrowRight') navLightbox(1);
                else if (e.key === 'Escape') closeLightbox();
                else if (e.key === 'r') restoreCurrent();
                else if (e.key === 'b' && lbIndex >= 0) toggleBoxes(document.getElementById('lbImg'), rows[lbIndex], { pct: 'aiy' });
            });

            async function restoreItem(id) {
                await fetch(`/api/sightings/${id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                showInfo('Restored to review');
                applyFilters();
            }
            
            async function restoreAll() {
                if (!confirm('Restore all currently-visible items to review?')) return;
                const params = new URLSearchParams({ review_status: 'rejected', sort_by: 'review_updated_at', limit: 200 });
                const dateFrom = document.getElementById('dateFrom').value;
                const dateTo = document.getElementById('dateTo').value;
                const species = document.getElementById('species').value;
                if (dateFrom) params.append('date_from', dateFrom);
                if (dateTo) params.append('date_to', dateTo);
                if (species) params.append('species', species);
                
                const res = await fetch(`/api/sightings?${params}`);
                const data = await res.json();
                for (const s of data.items) {
                    await fetch(`/api/sightings/${s.id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                }
                showInfo(`Restored ${data.items.length} items`);
                applyFilters();
            }
            
            async function emptyTrash() {
                if (!confirm('Permanently delete ALL trash (not just visible)? This cannot be undone.')) return;
                const btn = document.querySelector('button[onclick="emptyTrash()"]');
                const label = btn.textContent;
                btn.disabled = true;
                btn.textContent = 'Deleting...';
                let res;
                try {
                    res = await fetch('/api/trash-review/empty', { method: 'POST' });
                } finally {
                    btn.disabled = false;
                    btn.textContent = label;
                }
                const data = await res.json();
                let msg = `Permanently deleted ${data.permanently_deleted} items`;
                if (data.errors && data.errors.length) {
                    msg += ` - ${data.errors.length} failed: ${data.errors[0].filename}: ${data.errors[0].error}`;
                    console.log('Empty trash errors:', data.errors);
                }
                showInfo(msg);
                applyFilters();
            }
            
            function showInfo(msg) {
                const info = document.getElementById('info');
                info.textContent = msg;
                info.style.display = 'block';
                setTimeout(() => info.style.display = 'none', 4000);
            }
            
            loadSpecies();
            applyFilters();
        </script>
    </body>
    </html>
    """
    html = (html.replace("__NAV__", NAV_HTML).replace("__BOXES_CSS__", BOXES_CSS)
                .replace("__DBADGE_CSS__", DBADGE_CSS).replace("__BOXES_JS__", BOXES_JS))
    return HTMLResponse(html)
