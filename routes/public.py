import os
import io
import sqlite3
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from PIL import Image

router = APIRouter()


def _get_db_path():
    from main import DB_PATH
    return DB_PATH


def _get_data_dir():
    from main import DATA_DIR
    return DATA_DIR


def _get_crop_box():
    from main import PUBLIC_DISPLAY_CROP
    return PUBLIC_DISPLAY_CROP


@router.get("/api/public/species-list")
async def public_species_list():
    """Species that actually appear in APPROVED sightings only. Deliberately
    not reusing the admin /api/species-list, which also surfaces species from
    pending/rejected rows - the public page must never hint at the existence
    of photos that weren't approved."""
    conn = sqlite3.connect(_get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT COALESCE(common_name, species_aiy) AS label, species_aiy
        FROM sightings
        WHERE review_status = 'approved' AND species_aiy IS NOT NULL
        ORDER BY label
    """)
    species = [{"value": r[1], "label": r[0] or r[1]} for r in c.fetchall()]
    conn.close()
    return {"species": species}


@router.get("/api/public/sightings")
async def public_sightings(
    date_from: str = Query(None),
    date_to: str = Query(None),
    species: str = Query(None),
):
    """Read-only, unauthenticated, APPROVED ONLY.

    review_status='approved' is hardcoded into the WHERE clause and is NOT a
    client-supplied parameter - unlike the admin /api/sightings endpoint,
    there is no way for a caller to ask this endpoint for pending or rejected
    rows. Filters are accepted but only ever NARROW that fixed set.

    All filter values go in as bound parameters, never string-concatenated -
    this endpoint takes untrusted input straight off the public internet once
    Funnel is on, so it's the one place in the app where SQL injection would
    actually be reachable by a stranger.
    """
    sql = ["SELECT id, filename, timestamp, species_aiy, common_name",
           "FROM sightings WHERE review_status = 'approved'"]
    params = []

    if date_from:
        sql.append("AND date(timestamp) >= date(?)")
        params.append(date_from)
    if date_to:
        sql.append("AND date(timestamp) <= date(?)")
        params.append(date_to)
    if species:
        sql.append("AND species_aiy = ?")
        params.append(species)

    sql.append("ORDER BY timestamp DESC LIMIT 300")

    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(" ".join(sql), params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    # Thin payload on purpose: no confidence score, no review metadata, no
    # notes. Family doesn't need the classifier's internal uncertainty, and
    # it's one less thing that could ever leak or confuse.
    return {"items": [
        {"id": r["id"], "filename": r["filename"], "timestamp": r["timestamp"],
         "label": r["common_name"] or r["species_aiy"] or "Unknown bird",
         "species_aiy": r["species_aiy"]}
        for r in rows
    ]}


@router.get("/public-images/{filename}")
async def public_image(filename: str):
    """Privacy-cropped image, ONLY for sightings that are actually
    review_status='approved' - re-checked against the DB on every request,
    never trusted from the filename alone. Someone guessing or enumerating a
    filename that isn't approved gets a 404, never the image. That check is
    what makes the crop a real guarantee rather than "we remembered to crop
    it when building the page."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    conn = sqlite3.connect(_get_db_path())
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM sightings WHERE filename = ? AND review_status = 'approved'",
        (filename,)
    )
    is_approved = c.fetchone() is not None
    conn.close()
    if not is_approved:
        raise HTTPException(status_code=404, detail="Not found")

    image_path = os.path.join(_get_data_dir(), filename)
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Not found")

    img = Image.open(image_path).convert("RGB")
    img = img.crop(_get_crop_box())
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


# Built as a plain string with __PLACEHOLDER__ substitution rather than an
# f-string, matching gallery.py's pattern - the CSS/JS below is full of
# braces and f-string escaping would make it unreadable and error-prone.
FAMILY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Birdbath Visitors</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f5f5f5; padding: 20px; font-size: 17px; color: #222; }
        .container { max-width: 1500px; margin: 0 auto; background: white;
                     border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 24px; }
        h1 { margin-bottom: 4px; font-size: 30px; color: #2c3e50; }
        .tagline { color: #777; margin-bottom: 22px; font-size: 16px; }
        .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
                   gap: 15px; margin-bottom: 18px; padding: 16px; background: #fafafa; border-radius: 6px; }
        .filter-group { display: flex; flex-direction: column; }
        .filter-group label { font-size: 14px; font-weight: 600; color: #555; margin-bottom: 6px; }
        input[type="date"], select { padding: 11px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; }
        .controls { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        button { padding: 12px 20px; border: none; border-radius: 4px; font-size: 16px;
                 font-weight: 600; cursor: pointer; background: #007bff; color: white; }
        button:hover { background: #0056b3; }
        button.secondary { background: #6c757d; }
        #pageInfo { margin-bottom: 16px; color: #666; font-size: 16px; }
        .group-heading { font-size: 20px; font-weight: 600; margin: 28px 0 12px; color: #333;
                         border-bottom: 2px solid #eee; padding-bottom: 8px; }
        .group-heading:first-child { margin-top: 0; }
        /* Card size is driven by these two vars so the size selector can
           change both the column width and image height together. */
        .gallery { display: grid; gap: 18px; margin-bottom: 12px;
                   grid-template-columns: repeat(auto-fill, minmax(var(--card-w, 340px), 1fr)); }
        .gallery-item { position: relative; overflow: hidden; border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.12); background: #fff; }
        .gallery-item img { width: 100%; height: var(--card-h, 260px); object-fit: cover;
                            cursor: pointer; display: block; }
        .gallery-item:hover img { opacity: 0.9; }
        .gallery-label { position: absolute; bottom: 0; left: 0; right: 0;
                         background: rgba(0,0,0,0.72); color: white; padding: 11px 12px; font-size: 16px; }
        .gallery-label small { font-size: 14px; color: #ddd; }
    </style>
</head>
"""

FAMILY_HTML += """
<body>
    <div class="container">
        <h1>Birdbath Visitors</h1>
        <div class="tagline">Recent guests at the backyard birdbath</div>

        <div class="filters">
            <div class="filter-group"><label>Date From</label><input type="date" id="dateFrom"></div>
            <div class="filter-group"><label>Date To</label><input type="date" id="dateTo"></div>
            <div class="filter-group"><label>Bird</label>
                <select id="species"><option value="">All Birds</option></select>
            </div>
            <div class="filter-group"><label>Group By</label>
                <select id="groupBy" onchange="renderGallery()">
                    <option value="none">None</option>
                    <option value="date">Date</option>
                    <option value="species">Bird</option>
                </select>
            </div>
            <div class="filter-group"><label>Picture Size</label>
                <select id="sizeSel" onchange="applySize()">
                    <option value="m">Medium</option>
                    <option value="l" selected>Large</option>
                    <option value="xl">Extra Large</option>
                </select>
            </div>
        </div>

        <div class="controls">
            <button onclick="applyFilters()">Apply Filters</button>
            <button class="secondary" onclick="clearFilters()">Clear</button>
        </div>

        <div id="pageInfo"></div>
        <div id="galleryRoot"></div>
    </div>
"""

FAMILY_HTML += """
    <div class="lightbox" id="lightbox">
        <span class="lightbox-close" onclick="closeLightbox()" title="Close">&times;</span>
        <button class="lightbox-nav" style="left:20px;" onclick="navLightbox(-1)" title="Previous">&#8592;</button>
        <button class="lightbox-nav" style="right:20px;" onclick="navLightbox(1)" title="Next">&#8594;</button>
        <img id="lightboxImg">
        <div class="lightbox-info">
            <div id="lightboxCommon"></div>
            <div id="lightboxMeta"></div>
        </div>
    </div>
    <style>
        .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0;
                    width: 100%; height: 100%; background: rgba(0,0,0,0.93); }
        .lightbox.active { display: flex; align-items: center; justify-content: center; flex-direction: column; }
        .lightbox-close { position: absolute; top: 16px; right: 26px; color: white;
                          font-size: 46px; cursor: pointer; user-select: none; line-height: 1; }
        .lightbox-nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 34px;
                        padding: 20px 26px; background: rgba(255,255,255,0.18); color: white;
                        border: none; border-radius: 6px; cursor: pointer; }
        .lightbox-nav:hover { background: rgba(255,255,255,0.3); }
        .lightbox img { max-width: 94%; max-height: 80%; border-radius: 6px; }
        .lightbox-info { color: white; margin-top: 16px; text-align: center; padding: 0 20px; }
        #lightboxCommon { font-size: 26px; font-weight: 600; }
        #lightboxMeta { font-size: 16px; color: #ccc; margin-top: 6px; }
        @media (max-width: 600px) {
            body { padding: 12px; } .container { padding: 14px; } h1 { font-size: 25px; }
            .lightbox-nav { padding: 15px 18px; font-size: 27px; }
        }
    </style>
"""

FAMILY_HTML += """
    <script>
        let allSightings = [], flatList = [], lightboxIndex = -1;
        const SIZES = { m: ['260px','200px'], l: ['340px','260px'], xl: ['440px','340px'] };

        function applySize() {
            const [w, h] = SIZES[document.getElementById('sizeSel').value];
            document.documentElement.style.setProperty('--card-w', w);
            document.documentElement.style.setProperty('--card-h', h);
        }

        async function loadSpecies() {
            const res = await fetch('/api/public/species-list');
            const data = await res.json();
            const sel = document.getElementById('species');
            data.species.forEach(sp => {
                const opt = document.createElement('option');
                opt.value = sp.value; opt.textContent = sp.label;
                sel.appendChild(opt);
            });
        }

        async function loadSightings() {
            const params = new URLSearchParams();
            const df = document.getElementById('dateFrom').value;
            const dt = document.getElementById('dateTo').value;
            const sp = document.getElementById('species').value;
            if (df) params.append('date_from', df);
            if (dt) params.append('date_to', dt);
            if (sp) params.append('species', sp);

            const res = await fetch('/api/public/sightings?' + params);
            const data = await res.json();
            allSightings = data.items;
            const n = allSightings.length;
            document.getElementById('pageInfo').textContent =
                n + ' photo' + (n === 1 ? '' : 's');
            renderGallery();
        }

        function applyFilters() { loadSightings(); }

        function clearFilters() {
            document.getElementById('dateFrom').value = '';
            document.getElementById('dateTo').value = '';
            document.getElementById('species').value = '';
            document.getElementById('groupBy').value = 'none';
            loadSightings();
        }
"""

FAMILY_HTML += """
        function cardHtml(s, idx) {
            const date = new Date(s.timestamp).toLocaleDateString(undefined,
                { month: 'short', day: 'numeric', year: 'numeric' });
            return '<div class="gallery-item"><img loading="lazy" src="/public-images/' +
                   s.filename + '" onclick="openLightbox(' + idx + ')">' +
                   '<div class="gallery-label">' + s.label +
                   '<br><small>' + date + '</small></div></div>';
        }

        function renderGallery() {
            const root = document.getElementById('galleryRoot');
            root.innerHTML = ''; flatList = [];
            const groupBy = document.getElementById('groupBy').value;

            if (allSightings.length === 0) {
                root.innerHTML = '<p style="color:#999; text-align:center; padding:50px; font-size:18px;">' +
                                 'No visitors found - check back soon!</p>';
                return;
            }

            if (groupBy === 'none') {
                flatList = allSightings.slice();
                const grid = document.createElement('div');
                grid.className = 'gallery';
                flatList.forEach((s, i) => grid.insertAdjacentHTML('beforeend', cardHtml(s, i)));
                root.appendChild(grid);
                return;
            }

            const groups = {};
            allSightings.forEach(s => {
                const key = groupBy === 'date' ? s.timestamp.split('T')[0] : s.label;
                if (!groups[key]) groups[key] = [];
                groups[key].push(s);
            });
            const keys = Object.keys(groups).sort((a, b) =>
                groupBy === 'date' ? b.localeCompare(a) : a.localeCompare(b));
            keys.forEach(key => {
                const h = document.createElement('div');
                h.className = 'group-heading';
                h.textContent = groupBy === 'date'
                    ? new Date(key + 'T00:00:00').toLocaleDateString(undefined,
                        { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
                    : key;
                root.appendChild(h);
                const grid = document.createElement('div');
                grid.className = 'gallery';
                groups[key].forEach(s => {
                    const i = flatList.length; flatList.push(s);
                    grid.insertAdjacentHTML('beforeend', cardHtml(s, i));
                });
                root.appendChild(grid);
            });
        }
"""

FAMILY_HTML += """
        function openLightbox(i) {
            lightboxIndex = i; renderLightbox();
            document.getElementById('lightbox').classList.add('active');
        }
        function closeLightbox() {
            document.getElementById('lightbox').classList.remove('active');
            lightboxIndex = -1;
        }
        function renderLightbox() {
            if (lightboxIndex < 0 || lightboxIndex >= flatList.length) { closeLightbox(); return; }
            const s = flatList[lightboxIndex];
            document.getElementById('lightboxImg').src = '/public-images/' + s.filename;
            document.getElementById('lightboxCommon').textContent = s.label;
            const d = new Date(s.timestamp).toLocaleString(undefined,
                { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
                  hour: 'numeric', minute: '2-digit' });
            document.getElementById('lightboxMeta').textContent =
                d + '  (' + (lightboxIndex + 1) + ' of ' + flatList.length + ')';
        }
        function navLightbox(delta) {
            if (flatList.length === 0) return;
            lightboxIndex = (lightboxIndex + delta + flatList.length) % flatList.length;
            renderLightbox();
        }
        document.addEventListener('keydown', e => {
            if (!document.getElementById('lightbox').classList.contains('active')) return;
            if (e.key === 'ArrowLeft') navLightbox(-1);
            else if (e.key === 'ArrowRight') navLightbox(1);
            else if (e.key === 'Escape') closeLightbox();
        });

        applySize();
        loadSpecies().then(loadSightings);
    </script>
</body>
</html>
"""


@router.get("/family")
async def family_page():
    """Public, unauthenticated, read-only. Mirrors the admin Gallery's
    experience (filters, group-by, lightbox with arrow-key navigation) but
    with NO mutating actions - notably no "Send Back to Review" - no admin
    nav bar, and no links to Manage/Trash/Stats. A stranger with this URL
    should see a photo gallery and get no hint the admin workflow exists.
    Images come from /public-images/ (privacy-cropped, approval-checked),
    never /images/ (full-res originals, admin-only). Default card size is
    deliberately larger than the admin gallery's, with a size selector, since
    the intended audience includes older family members."""
    return HTMLResponse(FAMILY_HTML)
