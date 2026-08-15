from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

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
            .thumb { width: 50px; height: 50px; object-fit: cover; border-radius: 4px; }
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
        
        <script>
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
                if (data.items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Nothing here</td></tr>';
                    document.getElementById('trashCount').textContent = '';
                    return;
                }
                
                data.items.forEach(s => {
                    const tr = document.createElement('tr');
                    const rejectedDate = (s.review_updated_at || s.timestamp || '').split('T')[0];
                    tr.innerHTML = `<td><img src="/images/${s.filename}" class="thumb"></td><td>${s.species_aiy || 'Unknown'}</td><td>${(s.confidence_aiy * 100).toFixed(0)}%</td><td><small>${rejectedDate}</small></td><td><button class="btn-warning" onclick="restoreItem(${s.id})">Restore</button></td>`;
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
            
            async function restoreItem(id) {
                await fetch(`/api/sightings/${id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                showInfo('Restored to review');
                applyFilters();
            }
            
            async function restoreAll() {
                if (!confirm('Restore all currently-visible items to review?')) return;
                const params = new URLSearchParams({ review_status: 'rejected', sort_by: 'review_updated_at', limit: 1000 });
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
                const res = await fetch('/api/trash-review/empty', { method: 'POST' });
                const data = await res.json();
                showInfo(`Permanently deleted ${data.permanently_deleted} items`);
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
    html = html.replace("__NAV__", NAV_HTML)
    return HTMLResponse(html)
