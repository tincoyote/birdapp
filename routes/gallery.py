from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()

@router.get("/gallery")
async def gallery_page():
    """Gallery: approved sightings only. Browse by date/species, send back to review."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gallery - Approved Sightings</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
            .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
            h1 { margin-bottom: 20px; font-size: 24px; }
            .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; padding: 15px; background: #fafafa; border-radius: 6px; }
            .filter-group { display: flex; flex-direction: column; }
            .filter-group label { font-size: 12px; font-weight: 600; color: #666; margin-bottom: 5px; }
            input[type="date"], select { padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
            .controls { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
            button { padding: 10px 16px; border: none; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; background: #007bff; color: white; }
            button:hover { background: #0056b3; }
            .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
            .gallery-item { position: relative; overflow: hidden; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .gallery-item img { width: 100%; height: 200px; object-fit: cover; cursor: pointer; display: block; }
            .gallery-item:hover img { opacity: 0.85; }
            .gallery-label { position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.7); color: white; padding: 8px; font-size: 12px; }
            .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); }
            .lightbox.active { display: flex; align-items: center; justify-content: center; flex-direction: column; }
            .lightbox-close { position: absolute; top: 20px; right: 30px; color: white; font-size: 28px; cursor: pointer; user-select: none; }
            .lightbox img { max-width: 90%; max-height: 75%; border-radius: 4px; }
            .lightbox-info { color: white; margin-top: 15px; text-align: center; }
            button.send-review { background: #ffc107; color: black; margin-top: 12px; }
            button.send-review:hover { background: #e0a800; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Gallery - Approved Sightings</h1>
            __NAV__
            
            <div class="filters">
                <div class="filter-group"><label>Date From</label><input type="date" id="dateFrom"></div>
                <div class="filter-group"><label>Date To</label><input type="date" id="dateTo"></div>
                <div class="filter-group"><label>Species</label><select id="species"><option value="">All Species</option></select></div>
            </div>
            
            <div class="controls">
                <button onclick="applyFilters()">Apply Filters</button>
                <button onclick="clearFilters()" style="background: #6c757d;">Clear</button>
            </div>
            
            <div id="pageInfo" style="margin-bottom: 15px; color: #666;"></div>
            <div class="gallery" id="gallery"></div>
        </div>
        
        <div class="lightbox" id="lightbox">
            <span class="lightbox-close" onclick="closeLightbox()">&times;</span>
            <img id="lightboxImg">
            <div class="lightbox-info">
                <div id="lightboxLabel"></div>
                <button class="send-review" onclick="sendToReview()">Send Back to Review</button>
            </div>
        </div>
        
        <script>
            let currentSightingId = null;
            
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
                
                const params = new URLSearchParams({ review_status: 'approved', limit: 100 });
                if (dateFrom) params.append('date_from', dateFrom);
                if (dateTo) params.append('date_to', dateTo);
                if (species) params.append('species', species);
                
                const res = await fetch(`/api/sightings?${params}`);
                const data = await res.json();
                
                const gallery = document.getElementById('gallery');
                gallery.innerHTML = '';
                if (data.items.length === 0) {
                    gallery.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #999;">No sightings found</div>';
                    document.getElementById('pageInfo').textContent = '';
                    return;
                }
                
                data.items.forEach(s => {
                    const label = s.species_confirmed || s.species_aiy || 'Unknown';
                    const item = document.createElement('div');
                    item.className = 'gallery-item';
                    item.innerHTML = `<img src="/images/${s.filename}" onclick="openLightbox(${s.id}, '/images/${s.filename}', '${label}')"><div class="gallery-label">${label}<br>${(s.confidence_aiy * 100).toFixed(0)}%</div>`;
                    gallery.appendChild(item);
                });
                
                document.getElementById('pageInfo').textContent = `${data.items.length} approved sightings`;
            }
            
            function clearFilters() {
                document.getElementById('dateFrom').value = '';
                document.getElementById('dateTo').value = '';
                document.getElementById('species').value = '';
                applyFilters();
            }
            
            function openLightbox(id, imgSrc, label) {
                currentSightingId = id;
                document.getElementById('lightboxImg').src = imgSrc;
                document.getElementById('lightboxLabel').textContent = label;
                document.getElementById('lightbox').classList.add('active');
            }
            
            function closeLightbox() {
                document.getElementById('lightbox').classList.remove('active');
                currentSightingId = null;
            }
            
            async function sendToReview() {
                if (!currentSightingId) return;
                await fetch(`/api/sightings/${currentSightingId}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                closeLightbox();
                applyFilters();
            }
            
            loadSpecies();
            applyFilters();
        </script>
    </body>
    </html>
    """
    html = html.replace("__NAV__", NAV_HTML)
    return HTMLResponse(html)
