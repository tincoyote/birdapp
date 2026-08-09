import os
import sqlite3
import logging
import csv
import numpy as np
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import HTMLResponse
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


def classify_and_save(image_path, sighting_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE sightings SET status = 'identifying' WHERE id = ?", (sighting_id,))
    conn.commit()

    species_aiy, confidence_aiy = classify_aiy(image_path)

    # species_inat / confidence_inat intentionally left NULL for now.
    # iNaturalist small-model integration is a follow-up step, not yet wired in
    # (exact release asset filename wasn't confirmed yet).

    cursor.execute(
        "UPDATE sightings SET status = 'identified', species_aiy = ?, confidence_aiy = ? WHERE id = ?",
        (species_aiy, confidence_aiy, sighting_id)
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
