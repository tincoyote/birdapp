from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from routes.nav import NAV_HTML

router = APIRouter()

@router.get("/gallery")
async def gallery_page():
    """Gallery: approved sightings only. Browse by date/species, group either
    way, preview with next/prev navigation, send back to review."""
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
            .group-heading { font-size: 16px; font-weight: 600; margin: 24px 0 10px; color: #333; border-bottom: 2px solid #eee; padding-bottom: 6px; }
            .group-heading:first-child { margin-top: 0; }
            .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; margin-bottom: 10px; }
            .gallery-item { position: relative; overflow: hidden; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .gallery-item img { width: 100%; height: 200px; object-fit: cover; cursor: pointer; display: block; }
            .gallery-item:hover img { opacity: 0.85; }
            .gallery-label { position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.7); color: white; padding: 8px; font-size: 12px; }
            .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); }
            .lightbox.active { display: flex; align-items: center; justify-content: center; flex-direction: column; }
            .lightbox-close { position: absolute; top: 20px; right: 30px; color: white; font-size: 28px; cursor: pointer; user-select: none; }
            .lightbox-nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 28px; padding: 14px 18px; background: rgba(255,255,255,0.15); color: white; border: none; border-radius: 4px; cursor: pointer; }
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
                <div class="filter-group"><label>Group By</label>
                    <select id="groupBy" onchange="renderGallery()">
                        <option value="none">None</option>
                        <option value="date">Date</option>
                        <option value="species">Species</option>
                    </select>
                </div>
            </div>

            <div class="controls">
                <button onclick="applyFilters()">Apply Filters</button>
                <button onclick="clearFilters()" style="background: #6c757d;">Clear</button>
            </div>

            <div id="pageInfo" style="margin-bottom: 15px; color: #666;"></div>
            <div id="galleryRoot"></div>
        </div>


        <div class="lightbox" id="lightbox">
            <span class="lightbox-close" onclick="closeLightbox()">&times;</span>
            <button class="lightbox-nav" style="left:20px;" onclick="navLightbox(-1)">&#8592;</button>
            <button class="lightbox-nav" style="right:20px;" onclick="navLightbox(1)">&#8594;</button>
            <img id="lightboxImg">
            <div class="lightbox-info">
                <div id="lightboxCommon" style="font-size:20px; font-weight:600;"></div>
                <div id="lightboxMeta" style="font-size:13px; color:#ccc; margin-top:4px;"></div>
                <button class="send-review" onclick="sendBackToReview()">Send Back to Review</button>
            </div>
        </div>

        <script>
            let allSightings = [], flatList = [], lightboxIndex = -1;
            let speciesLabels = {};

            async function loadSpecies() {
                const res = await fetch('/api/species-list');
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
                return s.species_confirmed || s.common_name || speciesLabels[s.species_aiy] || s.species_aiy || 'Unknown';
            }

            async function applyFilters() {
                await loadSightings();
            }

            async function loadSightings() {
                const dateFrom = document.getElementById('dateFrom').value;
                const dateTo = document.getElementById('dateTo').value;
                const species = document.getElementById('species').value;

                const params = new URLSearchParams({ review_status: 'approved', page: 1, limit: 200 });
                if (dateFrom) params.append('date_from', dateFrom);
                if (dateTo) params.append('date_to', dateTo);
                if (species) params.append('species', species);

                const res = await fetch(`/api/sightings?${params}`);
                const data = await res.json();
                allSightings = data.items;
                document.getElementById('pageInfo').textContent = `${allSightings.length} sighting${allSightings.length === 1 ? '' : 's'}`;
                renderGallery();
            }

            function clearFilters() {
                document.getElementById('dateFrom').value = '';
                document.getElementById('dateTo').value = '';
                document.getElementById('species').value = '';
                document.getElementById('groupBy').value = 'none';
                applyFilters();
            }

            function cardHtml(s, flatIdx) {
                const common = commonName(s);
                return `<div class="gallery-item"><img src="/images/${s.filename}" onclick="openLightbox(${flatIdx})"><div class="gallery-label">${common}<br><small>${s.timestamp.split('T')[0]}</small></div></div>`;
            }

            function renderGallery() {
                const root = document.getElementById('galleryRoot');
                root.innerHTML = '';
                flatList = [];
                const groupBy = document.getElementById('groupBy').value;

                if (allSightings.length === 0) {
                    root.innerHTML = '<p style="color:#999; text-align:center; padding:40px;">No sightings found</p>';
                    return;
                }

                if (groupBy === 'none') {
                    flatList = allSightings.slice();
                    const grid = document.createElement('div');
                    grid.className = 'gallery';
                    flatList.forEach((s, idx) => grid.insertAdjacentHTML('beforeend', cardHtml(s, idx)));
                    root.appendChild(grid);
                    return;
                }

                const groups = {};
                allSightings.forEach(s => {
                    const key = groupBy === 'date' ? s.timestamp.split('T')[0] : commonName(s);
                    if (!groups[key]) groups[key] = [];
                    groups[key].push(s);
                });

                const keys = Object.keys(groups).sort((a, b) => groupBy === 'date' ? b.localeCompare(a) : a.localeCompare(b));
                keys.forEach(key => {
                    const heading = document.createElement('div');
                    heading.className = 'group-heading';
                    heading.textContent = key;
                    root.appendChild(heading);
                    const grid = document.createElement('div');
                    grid.className = 'gallery';
                    groups[key].forEach(s => {
                        const idx = flatList.length;
                        flatList.push(s);
                        grid.insertAdjacentHTML('beforeend', cardHtml(s, idx));
                    });
                    root.appendChild(grid);
                });
            }

            function openLightbox(idx) {
                lightboxIndex = idx;
                renderLightbox();
                document.getElementById('lightbox').classList.add('active');
            }

            function closeLightbox() {
                document.getElementById('lightbox').classList.remove('active');
                lightboxIndex = -1;
            }

            function renderLightbox() {
                if (lightboxIndex < 0 || lightboxIndex >= flatList.length) { closeLightbox(); return; }
                const s = flatList[lightboxIndex];
                document.getElementById('lightboxImg').src = `/images/${s.filename}`;
                document.getElementById('lightboxCommon').textContent = commonName(s);
                document.getElementById('lightboxMeta').textContent =
                    `${s.species_aiy || 'Unknown'} - ${(s.confidence_aiy * 100).toFixed(0)}% - ${s.timestamp.split('T')[0]} (${lightboxIndex + 1} of ${flatList.length})`;
            }

            function navLightbox(delta) {
                if (flatList.length === 0) return;
                lightboxIndex = (lightboxIndex + delta + flatList.length) % flatList.length;
                renderLightbox();
            }

            async function sendBackToReview() {
                if (lightboxIndex < 0) return;
                const s = flatList[lightboxIndex];
                await fetch(`/api/sightings/${s.id}/review-status`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_status: 'pending_review'}) });
                allSightings = allSightings.filter(x => x.id !== s.id);
                closeLightbox();
                renderGallery();
            }

            document.addEventListener('keydown', e => {
                if (!document.getElementById('lightbox').classList.contains('active')) return;
                if (e.key === 'ArrowLeft') navLightbox(-1);
                else if (e.key === 'ArrowRight') navLightbox(1);
                else if (e.key === 'Escape') closeLightbox();
            });

            loadSpecies().then(loadSightings);
        </script>
    </body>
    </html>
    """
    html = html.replace("__NAV__", NAV_HTML)
    return HTMLResponse(html)
