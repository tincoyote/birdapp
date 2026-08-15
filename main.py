import os
import sqlite3
import logging
import csv
import numpy as np
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse
from migration import migrate_v1_to_v2

# Manage page HTML
manage_page_html = """<!DOCTYPE html>
<html>
<head>
    <title>Manage Sightings</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
        h1 { margin-bottom: 20px; font-size: 24px; }
        .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; padding: 15px; background: #fafafa; border-radius: 6px; }
        .filter-group { display: flex; flex-direction: column; }
        .filter-group label { font-size: 12px; font-weight: 600; color: #666; margin-bottom: 5px; }
        input[type="text"], input[type="date"], input[type="range"], select { padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
        .controls { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }
        button { padding: 10px 16px; border: none; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; }
        .btn-primary { background: #007bff; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .pagination { display: flex; gap: 10px; align-items: center; }
        .table-wrapper { overflow-x: auto; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f8f9fa; padding: 12px; text-align: left; font-weight: 600; font-size: 13px; border-bottom: 2px solid #dee2e6; }
        td { padding: 12px; border-bottom: 1px solid #dee2e6; }
        tr:hover { background: #f9f9f9; }
        .thumb { width: 50px; height: 50px; object-fit: cover; cursor: pointer; border-radius: 4px; }
        .status { display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }
        .status.identified { background: #d4edda; color: #155724; }
        .status.trashed { background: #f8d7da; color: #721c24; }
        .lightbox { display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); }
        .lightbox.active { display: flex; align-items: center; justify-content: center; }
        .lightbox img { max-width: 90%; max-height: 90%; }
        .lightbox-close { position: absolute; top: 20px; right: 30px; color: white; font-size: 28px; cursor: pointer; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
        .modal.active { display: flex; align-items: center; justify-content: center; }
        .modal-content { background: white; padding: 30px; border-radius: 8px; min-width: 300px; }
        .modal-content h2 { margin-bottom: 15px; }
        .modal-content input { width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; }
        .modal-buttons { display: flex; gap: 10px; justify-content: flex-end; }
        .info { padding: 12px; background: #e7f3ff; border-left: 4px solid #007bff; margin-bottom: 15px; font-size: 13px; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Manage Sightings</h1>
        <div class="info" id="info"></div>
        <div class="filters">
            <div class="filter-group"><label>Date From</label><input type="date" id="dateFrom"></div>
            <div class="filter-group"><label>Date To</label><input type="date" id="dateTo"></div>
            <div class="filter-group"><label>Species</label><select id="species"><option value="">All Species</option></select></div>
            <div class="filter-group"><label>Min Confidence: <span id="confLabel">0%</span></label><input type="range" id="confidence" min="0" max="100" value="0"></div>
        </div>
        <div class="controls">
            <button class="btn-primary" onclick="applyFilters()">Apply Filters</button>
            <button class="btn-secondary" onclick="clearFilters()">Clear</button>
            <span id="selectedCount" style="margin-left: auto; color: #666;"></span>
        </div>
        <div class="controls">
            <button class="btn-success" onclick="markFavorite()" id="btnFav" disabled>★ Favorite</button>
            <button class="btn-primary" onclick="retag()" id="btnRetag" disabled>Retag</button>
            <button class="btn-danger" onclick="deleteSelected()" id="btnDel" disabled>Delete</button>
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
                        <th>Species</th>
                        <th style="width:90px;">Confidence</th>
                        <th style="width:140px;">Date</th>
                        <th style="width:80px;">Status</th>
                    </tr>
                </thead>
                <tbody id="tbody"><tr><td colspan="6" style="text-align:center; padding:40px; color:#999;">Loading...</td></tr></tbody>
            </table>
        </div>
    </div>
    <div class="lightbox" id="lightbox" onclick="closeLightbox()">
        <span class="lightbox-close" onclick="event.stopPropagation()">&times;</span>
        <img id="lightboxImg" onclick="event.stopPropagation()">
    </div>
    <div class="modal" id="retagModal">
        <div class="modal-content">
            <h2>Retag Selected</h2>
            <label>New Species Name:</label>
            <input type="text" id="retagInput" placeholder="e.g., American Robin">
            <div class="modal-buttons">
                <button class="btn-secondary" onclick="closeRetagModal()">Cancel</button>
                <button class="btn-primary" onclick="executeRetag()">Retag</button>
            </div>
        </div>
    </div>
    <script>
        let currentPage = 1, allSightings = [], selectedIds = new Set();
        async function loadSpecies() { const res = await fetch('/api/species-list'); const data = await res.json(); const sel = document.getElementById('species'); data.species.forEach(sp => { const opt = document.createElement('option'); opt.value = opt.textContent = sp; sel.appendChild(opt); }); }
        async function applyFilters() { currentPage = 1; selectedIds.clear(); document.getElementById('selectAll').checked = false; updateSelectedCount(); await loadSightings(); }
        async function loadSightings() { const dateFrom = document.getElementById('dateFrom').value; const dateTo = document.getElementById('dateTo').value; const species = document.getElementById('species').value; const conf = parseInt(document.getElementById('confidence').value) / 100; const perPage = parseInt(document.getElementById('perPage').value); const params = new URLSearchParams({ confidence_min: conf, confidence_max: 1.0, page: currentPage, limit: perPage }); if (dateFrom) params.append('date_from', dateFrom); if (dateTo) params.append('date_to', dateTo); if (species) params.append('species', species); const res = await fetch(`/api/sightings?${params}`); const data = await res.json(); allSightings = data.items; const tbody = document.getElementById('tbody'); tbody.innerHTML = ''; if (allSightings.length === 0) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:40px; color:#999;">No sightings found</td></tr>'; document.getElementById('pageInfo').textContent = 'No results'; return; } allSightings.forEach(s => { const statusClass = s.is_trashed ? 'trashed' : 'identified'; const tr = document.createElement('tr'); tr.innerHTML = `<td><input type="checkbox" value="${s.id}" onchange="updateSelectedCount()"></td><td><img src="/images/${s.filename}" class="thumb" onclick="showLightbox('/images/${s.filename}')"></td><td>${s.species_confirmed || s.species_aiy || 'Unknown'}</td><td>${(s.confidence_aiy * 100).toFixed(0)}%</td><td><small>${s.timestamp}</small></td><td><span class="status ${statusClass}">${s.is_trashed ? 'Trashed' : 'Identified'}</span></td>`; tbody.appendChild(tr); }); const totalPages = Math.ceil(data.total / perPage); document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages} (${data.total} total)`; }
        function toggleSelectAll() { const checked = document.getElementById('selectAll').checked; document.querySelectorAll('tbody input[type="checkbox"]').forEach(cb => cb.checked = checked); updateSelectedCount(); }
        function updateSelectedCount() { selectedIds.clear(); document.querySelectorAll('tbody input[type="checkbox"]:checked').forEach(cb => selectedIds.add(parseInt(cb.value))); document.getElementById('selectedCount').textContent = selectedIds.size + ' selected'; ['btnDel', 'btnRetag', 'btnFav'].forEach(id => document.getElementById(id).disabled = selectedIds.size === 0); }
        function showLightbox(src) { document.getElementById('lightboxImg').src = src; document.getElementById('lightbox').classList.add('active'); }
        function closeLightbox() { document.getElementById('lightbox').classList.remove('active'); }
        function clearFilters() { document.getElementById('dateFrom').value = document.getElementById('dateTo').value = document.getElementById('species').value = ''; document.getElementById('confidence').value = 0; document.getElementById('confLabel').textContent = '0%'; applyFilters(); }
        async function deleteSelected() { if (!confirm(`Move ${selectedIds.size} sighting(s) to trash?`)) return; const res = await fetch('/api/sightings/delete-filtered', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filters: {}}) }); const data = await res.json(); showInfo(`Moved ${data.trashed} to trash`); selectedIds.clear(); await applyFilters(); }
        function retag() { document.getElementById('retagModal').classList.add('active'); document.getElementById('retagInput').focus(); }
        function closeRetagModal() { document.getElementById('retagModal').classList.remove('active'); }
        async function executeRetag() { const newSpecies = document.getElementById('retagInput').value.trim(); if (!newSpecies) { alert('Enter a species name'); return; } const res = await fetch('/api/sightings/retag', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filters: {}, new_species: newSpecies}) }); const data = await res.json(); showInfo(`Retagged ${data.retagged} to "${newSpecies}"`); closeRetagModal(); selectedIds.clear(); await applyFilters(); }
        function markFavorite() { showInfo(`Marked ${selectedIds.size} as favorite (coming soon)`); }
        function showInfo(msg) { const info = document.getElementById('info'); info.textContent = msg; info.style.display = 'block'; setTimeout(() => info.style.display = 'none', 4000); }
        document.getElementById('confidence').addEventListener('input', e => document.getElementById('confLabel').textContent = e.target.value + '%');
        loadSpecies(); applyFilters();
    </script>
</body>
</html>
"""
from fastapi.staticfiles import StaticFiles
from PIL import Image
import tflite_runtime.interpreter as tflite

app = FastAPI()

DATA_DIR = "/app/data/images"
DB_PATH = "/app/data/birds.db"
MODEL_DIR = "/app/models"
AIY_MODEL_PATH = os.path.join(MODEL_DIR, "aiy_birds_v1.tflite")
AIY_LABELS_PATH = os.path.join(MODEL_DIR, "aiy_birds_labelmap.csv")

os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("birdapp")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            filename TEXT,
            status TEXT DEFAULT 'acquired',
            species_aiy TEXT,
            confidence_aiy REAL,
            species_inat TEXT,
            confidence_inat REAL,
            species_confirmed TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()
migrate_v1_to_v2(DB_PATH)

# --- AIY (Google) bird classifier: loads once at startup, fails soft if files are missing ---
aiy_interpreter = None
aiy_labels = {}
aiy_input_details = None
aiy_output_details = None


def load_aiy_model():
    global aiy_interpreter, aiy_labels, aiy_input_details, aiy_output_details
    try:
        aiy_interpreter = tflite.Interpreter(model_path=AIY_MODEL_PATH)
        aiy_interpreter.allocate_tensors()
        aiy_input_details = aiy_interpreter.get_input_details()
        aiy_output_details = aiy_interpreter.get_output_details()
        with open(AIY_LABELS_PATH, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                try:
                    idx = int(row[0])
                except ValueError:
                    continue  # skip a header row if the CSV has one
                aiy_labels[idx] = row[1] if len(row) > 1 else str(idx)
        logger.info(
            "AIY bird model loaded: %d labels, input shape %s, dtype %s",
            len(aiy_labels), aiy_input_details[0]['shape'], aiy_input_details[0]['dtype']
        )
    except Exception as e:
        logger.error("Failed to load AIY model (classification will be skipped): %s", e)


load_aiy_model()

@app.get("/manage")
async def manage_page():
    return HTMLResponse(manage_page_html)

def classify_aiy(image_path):
    """Run the Google AIY bird classifier. Returns (species, confidence) or (None, None) if unavailable.
    Reads the model's own input dtype at runtime instead of assuming float vs. quantized,
    so this adapts correctly whether the model turns out to be float32 or uint8 quantized."""
    if aiy_interpreter is None:
        return None, None
    try:
        _, height, width, _ = aiy_input_details[0]['shape']
        img = Image.open(image_path).convert("RGB").resize((width, height))
        arr = np.array(img)

        input_dtype = aiy_input_details[0]['dtype']
        if input_dtype == np.float32:
            input_data = np.expand_dims(arr.astype(np.float32) / 255.0, axis=0)
        else:
            input_data = np.expand_dims(arr.astype(input_dtype), axis=0)

        aiy_interpreter.set_tensor(aiy_input_details[0]['index'], input_data)
        aiy_interpreter.invoke()
        output = aiy_interpreter.get_tensor(aiy_output_details[0]['index'])[0]

        output_dtype = aiy_output_details[0]['dtype']
        if output_dtype != np.float32:
            scale, zero_point = aiy_output_details[0]['quantization']
            output = (output.astype(np.float32) - zero_point) * scale if scale else output.astype(np.float32)

        top_idx = int(np.argmax(output))
        confidence = float(output[top_idx])
        species = aiy_labels.get(top_idx, f"Unknown (class {top_idx})")
        return species, confidence
    except Exception as e:
        logger.exception("AIY classification failed: %s", e)
        return None, None


def compute_agreement(species_aiy, confidence_aiy, species_inat, confidence_inat):
    """Determine classifier_agreement state from two classifiers' output.
    Handles the case where one classifier hasn't run / isn't wired in yet -
    that's 'one_classifier', distinct from 'pending' (both still running)."""
    if species_aiy and not species_inat:
        return 'one_classifier'
    if species_inat and not species_aiy:
        return 'one_classifier'
    if not species_aiy and not species_inat:
        return 'pending'

    if species_aiy == species_inat:
        if confidence_aiy >= 0.75 and confidence_inat >= 0.75:
            return 'agreed'
        return 'low_confidence'
    return 'disagreed'


def classify_and_save(image_path, sighting_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE sightings SET status = 'identifying' WHERE id = ?", (sighting_id,))
    conn.commit()

    species_aiy, confidence_aiy = classify_aiy(image_path)

    # species_inat / confidence_inat intentionally left NULL for now.
    # iNaturalist small-model integration is a follow-up step, not yet wired in
    # (exact release asset filename wasn't confirmed yet).
    species_inat, confidence_inat = None, None

    agreement = compute_agreement(species_aiy, confidence_aiy, species_inat, confidence_inat)

    cursor.execute(
        """UPDATE sightings
           SET status = 'identified', species_aiy = ?, confidence_aiy = ?,
               species_inat = ?, confidence_inat = ?, classifier_agreement = ?
           WHERE id = ?""",
        (species_aiy, confidence_aiy, species_inat, confidence_inat, agreement, sighting_id)
    )
    conn.commit()
    conn.close()


@app.post("/webhook")
async def motion_webhook(background_tasks: BackgroundTasks, image: UploadFile = File(...), message: str = Form(None)):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bird_{timestamp}.jpg"
    image_path = os.path.join(DATA_DIR, filename)

    try:
        contents = await image.read()
        with open(image_path, "wb") as f:
            f.write(contents)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sightings (timestamp, filename, status) VALUES (?, ?, 'acquired')",
            (datetime.now().isoformat(), filename)
        )
        sighting_id = cursor.lastrowid
        conn.commit()
        conn.close()

        background_tasks.add_task(classify_and_save, image_path, sighting_id)
        return {"status": "success", "file": filename, "id": sighting_id}
    except Exception as e:
        logger.exception("webhook error")
        return {"status": "error", "message": str(e)}


app.mount("/images", StaticFiles(directory=DATA_DIR), name="images")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, filename, status, species_aiy, confidence_aiy, species_confirmed "
        "FROM sightings ORDER BY id DESC LIMIT 20"
    )
    rows = cursor.fetchall()
    conn.close()

    html = """
    <html>
        <head>
            <title>Birdbath AI Classifier</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; background: #f4f4f9; color: #333; }
                h1 { color: #2c3e50; }
                .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; }
                .card { background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                img { width: 100%; height: 160px; object-fit: cover; border-radius: 4px; }
                .status { font-size: 0.8em; color: #888; }
            </style>
        </head>
        <body>
            <h1>🐦 Birdbath Visitor Dashboard</h1>
            <div class="grid">
    """
    for row in rows:
        ts, fn, status, species_aiy, confidence_aiy, species_confirmed = row
        display_species = species_confirmed or species_aiy or "Unidentified"
        conf_str = f"{confidence_aiy:.0%}" if confidence_aiy is not None else ""
        html += f"""
            <div class="card">
                <img src="/images/{fn}" />
                <h3>{display_species}</h3>
                <p><small>{ts}</small></p>
                <p class="status">status: {status} {conf_str}</p>
            </div>
        """
    html += """
            </div>
        </body>
    </html>
    """
    return html


def _build_filter_where(f: dict):
    """Shared WHERE-clause builder for filter/delete/retag - keeps filter
    semantics identical across all three endpoints."""
    where_parts = ["is_trashed = 0"]
    params = []
    if f.get("species"):
        where_parts.append("(species_confirmed = ? OR (species_confirmed IS NULL AND species_aiy = ?))")
        params.extend([f["species"], f["species"]])
    if f.get("confidence_min") is not None or f.get("confidence_max") is not None:
        where_parts.append("confidence_aiy BETWEEN ? AND ?")
        params.extend([f.get("confidence_min", 0.0), f.get("confidence_max", 1.0)])
    if f.get("inbox_status"):
        where_parts.append("inbox_status = ?")
        params.append(f["inbox_status"])
    if f.get("date_from"):
        where_parts.append("timestamp >= ?")
        params.append(f["date_from"] + "T00:00:00")
    if f.get("date_to"):
        where_parts.append("timestamp <= ?")
        params.append(f["date_to"] + "T23:59:59")
    return " AND ".join(where_parts), params


@app.get("/api/sightings")
async def list_sightings(
    confidence_min: float = Query(0.0, ge=0, le=1),
    confidence_max: float = Query(1.0, ge=0, le=1),
    species: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    inbox_status: str = Query(None),
    is_trashed: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    where_parts = ["is_trashed = ?"]
    params = [1 if is_trashed else 0]
    if species:
        where_parts.append("(species_confirmed = ? OR (species_confirmed IS NULL AND species_aiy = ?))")
        params.extend([species, species])
    if confidence_min > 0 or confidence_max < 1:
        where_parts.append("confidence_aiy BETWEEN ? AND ?")
        params.extend([confidence_min, confidence_max])
    if inbox_status:
        where_parts.append("inbox_status = ?")
        params.append(inbox_status)
    if date_from:
        where_parts.append("timestamp >= ?")
        params.append(date_from + "T00:00:00")
    if date_to:
        where_parts.append("timestamp <= ?")
        params.append(date_to + "T23:59:59")

    where_clause = " AND ".join(where_parts)

    cursor.execute(f"SELECT COUNT(*) FROM sightings WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    offset = (page - 1) * limit
    cursor.execute(
        f"""SELECT * FROM sightings WHERE {where_clause}
           ORDER BY is_favorite DESC, timestamp DESC
           LIMIT ? OFFSET ?""",
        params + [limit, offset]
    )
    rows = cursor.fetchall()
    conn.close()
    return {"total": total, "page": page, "limit": limit, "items": [dict(r) for r in rows]}


@app.post("/api/sightings/delete-filtered")
async def delete_filtered(filters: dict):
    """Move matching sightings to trash (is_trashed=1). Reversible - files
    are untouched. Permanent removal only happens via /api/trash/empty."""
    where_clause, params = _build_filter_where(filters)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE sightings SET is_trashed = 1 WHERE {where_clause}", params)
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return {"trashed": count}


@app.post("/api/sightings/retag")
async def retag_filtered(payload: dict):
    """Body: {"filters": {...}, "new_species": "..."}. Sets species_confirmed
    on every sighting matching the filters."""
    filters = payload.get("filters", {})
    new_species = payload.get("new_species")
    if not new_species:
        return {"error": "new_species is required"}
    where_clause, params = _build_filter_where(filters)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE sightings SET species_confirmed = ? WHERE {where_clause}",
        [new_species] + params
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return {"retagged": count}


@app.post("/api/trash/empty")
async def empty_trash():
    """Permanently delete trashed sightings AND their image files. Not reversible."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename FROM sightings WHERE is_trashed = 1")
    rows = cursor.fetchall()
    deleted = 0
    for sighting_id, filename in rows:
        image_path = os.path.join(DATA_DIR, filename)
        if os.path.exists(image_path):
            os.remove(image_path)
        cursor.execute("DELETE FROM sightings WHERE id = ?", (sighting_id,))
        deleted += 1
    conn.commit()
    conn.close()
    return {"permanently_deleted": deleted}


@app.get("/api/stats")
async def stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM sightings WHERE is_trashed=0")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sightings WHERE is_trashed=0 AND confidence_aiy < 0.5")
    low_conf = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sightings WHERE is_trashed=1")
    trashed = cursor.fetchone()[0]

    cursor.execute("""
        SELECT species_aiy, COUNT(*) as count
        FROM sightings
        WHERE is_trashed=0 AND confidence_aiy > 0.5
        GROUP BY species_aiy
        ORDER BY count DESC
        LIMIT 5
    """)
    top_species = [{"species": r[0], "count": r[1]} for r in cursor.fetchall()]

    conn.close()
    return {
        "total_sightings": total,
        "low_confidence_count": low_conf,
        "trashed_count": trashed,
        "top_species": top_species
    }


@app.get("/api/species-list")
async def species_list():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT species_confirmed FROM sightings
        WHERE is_trashed=0 AND species_confirmed IS NOT NULL
        UNION
        SELECT DISTINCT species_aiy FROM sightings
        WHERE is_trashed=0 AND species_aiy IS NOT NULL AND species_aiy != 'background'
        ORDER BY 1
    """)
    species = [row[0] for row in cursor.fetchall()]
    conn.close()
    return {"species": species}
