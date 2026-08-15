from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/trash")
async def trash_page():
    """Trash: rejected sightings. Review, restore, or permanently delete."""
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
            .controls { display: flex; gap: 10px; margin-bottom: 20px; }
            .info { padding: 12px; background: #f8d7da; border-left: 4px solid #dc3545; margin-bottom: 15px; font-size: 13px; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Trash - Review Before Delete</h1>
            <div class="info" id="info"></div>
            
            <div class="controls">
                <button class="btn-warning" onclick="restoreAll()">Restore All</button>
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
                            <th style="width:140px;">Date</th>
                            <th style="width:100px;">Action</th>
                        </tr>
                    </thead>
                    <tbody id="tbody"><tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Loading...</td></tr></tbody>
                </table>
            </div>
        </div>
        
        <script>
            async function loadTrash() {
                const res = await fetch('/api/sightings?review_status=rejected&limit=100');
                const data = await res.json();
                
                const tbody = document.getElementById('tbody');
                tbody.innerHTML = '';
                if (data.items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:#999;">Trash is empty</td></tr>';
                    document.getElementById('trashCount').textContent = '';
                    return;
                }
                
                data.items.forEach(s => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td><img src="/images/${s.filename}" class="thumb"></td><td>${s.species_aiy || 'Unknown'}</td><td>${(s.confidence_aiy * 100).toFixed(0)}%</td><td><small>${s.timestamp.split('T')[0]}</small></td><td><button class="btn-warning" onclick="restoreItem(${s.id})">Restore</button></td>`;
                    tbody.appendChild(tr);
                });
                
                document.getElementById('trashCount').textContent = `${data.total} items in trash`;
            }
            
            async function restoreItem(id) {
                await fetch(`/api/sightings/${id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                showInfo('Restored to review');
                loadTrash();
            }
            
            async function restoreAll() {
                if (!confirm('Restore all items to review?')) return;
                const res = await fetch('/api/sightings?review_status=rejected&limit=1000');
                const data = await res.json();
                for (const s of data.items) {
                    await fetch(`/api/sightings/${s.id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                }
                showInfo(`Restored ${data.items.length} items`);
                loadTrash();
            }
            
            async function emptyTrash() {
                if (!confirm('Permanently delete all trash? This cannot be undone.')) return;
                const res = await fetch('/api/trash-review/empty', { method: 'POST' });
                const data = await res.json();
                showInfo(`Permanently deleted ${data.permanently_deleted} items`);
                loadTrash();
            }
            
            function showInfo(msg) {
                const info = document.getElementById('info');
                info.textContent = msg;
                info.style.display = 'block';
                setTimeout(() => info.style.display = 'none', 4000);
            }
            
            loadTrash();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
