from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/manage")
async def manage_page():
    """Bulk review of pending_review sightings. Filter, batch Accept/Resend/Delete."""
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
            .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); }
            .lightbox.active { display: flex; align-items: center; justify-content: center; }
            .lightbox img { max-width: 90%; max-height: 90%; border-radius: 4px; }
            .lightbox-close { position: absolute; top: 20px; right: 30px; color: white; font-size: 28px; cursor: pointer; user-select: none; }
            .info { padding: 12px; background: #e7f3ff; border-left: 4px solid #007bff; margin-bottom: 15px; font-size: 13px; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Manage - Review Sightings</h1>
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
                <button class="btn-success" onclick="acceptSelected()" id="btnAccept" disabled>✓ Accept to Gallery</button>
                <button class="btn-primary" onclick="resendSelected()" id="btnResend" disabled>↻ Resend to Classifier</button>
                <button class="btn-danger" onclick="deleteSelected()" id="btnDel" disabled>🗑 Reject to Trash</button>
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
                            <th>Species (Latin)</th>
                            <th style="width:90px;">Confidence</th>
                            <th style="width:140px;">Date</th>
                        </tr>
                    </thead>
                    <tbody id="tbody"><tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Loading...</td></tr></tbody>
                </table>
            </div>
        </div>
        
        <div class="lightbox" id="lightbox">
            <span class="lightbox-close" onclick="closeLightbox()">&times;</span>
            <img id="lightboxImg" onclick="event.stopPropagation()">
        </div>
        
        <script>
            let currentPage = 1, allSightings = [], selectedIds = new Set();
            
            async function loadSpecies() {
                const res = await fetch('/api/species-list');
                const data = await res.json();
                const sel = document.getElementById('species');
                data.species.forEach(sp => {
                    const opt = document.createElement('option');
                    opt.value = opt.textContent = sp;
                    sel.appendChild(opt);
                });
            }
            
            async function autoPopulateDates() {
                const res = await fetch('/api/sightings?review_status=pending_review&limit=1');
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
                    review_status: 'pending_review'
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
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">No sightings found</td></tr>';
                    document.getElementById('pageInfo').textContent = 'No results';
                    return;
                }
                
                allSightings.forEach(s => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td><input type="checkbox" value="${s.id}" onchange="updateSelectedCount()"></td><td><img src="/images/${s.filename}" class="thumb" onclick="showLightbox('/images/${s.filename}')"></td><td>${s.species_aiy || 'Unknown'}</td><td>${(s.confidence_aiy * 100).toFixed(0)}%</td><td><small>${s.timestamp.split('T')[0]}</small></td>`;
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
            
            function showLightbox(src) {
                document.getElementById('lightboxImg').src = src;
                document.getElementById('lightbox').classList.add('active');
            }
            
            function closeLightbox() {
                document.getElementById('lightbox').classList.remove('active');
            }
            
            function clearFilters() {
                document.getElementById('dateFrom').value = '';
                document.getElementById('dateTo').value = '';
                document.getElementById('species').value = '';
                document.getElementById('confidence').value = 100;
                document.getElementById('confLabel').textContent = '100%';
                applyFilters();
            }
            
            async function acceptSelected() {
                if (!confirm(`Accept ${selectedIds.size} to gallery?`)) return;
                const ids = Array.from(selectedIds);
                for (const id of ids) {
                    await fetch(`/api/sightings/${id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'approved'}) });
                }
                showInfo(`Accepted ${ids.length} to gallery`);
                selectedIds.clear();
                await applyFilters();
            }
            
            async function resendSelected() {
                if (!confirm(`Resend ${selectedIds.size} to classifier?`)) return;
                const ids = Array.from(selectedIds);
                for (const id of ids) {
                    await fetch(`/api/sightings/${id}/resend-classifier`, { method: 'POST' });
                }
                showInfo(`Sent ${ids.length} to classifier`);
                selectedIds.clear();
                await applyFilters();
            }
            
            async function deleteSelected() {
                if (!confirm(`Reject ${selectedIds.size} to trash?`)) return;
                const ids = Array.from(selectedIds);
                for (const id of ids) {
                    await fetch(`/api/sightings/${id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'rejected'}) });
                }
                showInfo(`Rejected ${ids.length} to trash`);
                selectedIds.clear();
                await applyFilters();
            }
            
            function showInfo(msg) {
                const info = document.getElementById('info');
                info.textContent = msg;
                info.style.display = 'block';
                setTimeout(() => info.style.display = 'none', 4000);
            }
            
            document.getElementById('confidence').addEventListener('input', e => document.getElementById('confLabel').textContent = e.target.value + '%');
            loadSpecies();
            autoPopulateDates();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
