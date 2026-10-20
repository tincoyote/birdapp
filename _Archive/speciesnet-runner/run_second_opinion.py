"""
run_second_opinion.py

Pulls sightings that are queued for a second classifier opinion from
birdapp's own API, runs SpeciesNet on them locally (this laptop, not the
NAS), and POSTs each result back to birdapp's /second-opinion endpoint.

Deliberately never opens birds.db directly. That file lives on the NAS and
the running birdapp container has it open continuously; a second process
opening the same SQLite file over a network share (S:\\birdapp\\data) is not
something SQLite's locking reliably supports. Going through the HTTP API
keeps the container as the only writer, always.

Credentials are read directly from birdapp's own .env file (BIRDAPP_ENV_PATH
below) rather than duplicated into a second config - one canonical secrets
file, same as birdapp itself uses. Add API_USERNAME/API_PASSWORD to that
.env yourself; this script never chooses or stores real credential values,
it only reads whatever's already there.

Usage:
    .venv\\Scripts\\python.exe run_second_opinion.py --limit 50
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# EDIT THESE THREE VALUES for your own setup before running this script.
# They point at wherever YOUR birdapp instance actually lives - the values
# below are specific to one particular deployment and will not work as-is
# anywhere else. See SETUP.md in the birdapp repo for the full walkthrough.
# ---------------------------------------------------------------------------
BIRDAPP_BASE_URL = "https://birdapp.localsleeve.com"      # <-- your birdapp's URL
BIRDAPP_ENV_PATH = Path(r"S:\birdapp\.env")                # <-- path to your birdapp's .env
CAMERA_CONFIG_PATH = Path(r"S:\birdapp\camera_config.json")  # <-- path to your birdapp's camera_config.json
# ---------------------------------------------------------------------------

VENV_PYTHON = sys.executable  # assumes this script is run via the venv's python


def load_env(path: Path) -> dict:
    """Minimal .env parser - KEY=VALUE per line, '#' comments, blank lines
    ignored. Avoids adding python-dotenv as a dependency for something this
    small, and keeps this script's only dependency on birdapp's secrets
    file being a plain read, nothing fancier."""
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


try:
    _env = load_env(BIRDAPP_ENV_PATH)
except FileNotFoundError:
    print(f"Can't find {BIRDAPP_ENV_PATH} - is the S: drive mapped and connected?")
    sys.exit(1)
ADMIN_USER = _env.get("API_USERNAME") or _env.get("ADMIN_USERNAME", "")
ADMIN_PASS = _env.get("API_PASSWORD") or _env.get("ADMIN_PASSWORD", "")

try:
    CLASSIFIER_CROP_BOX = tuple(json.loads(CAMERA_CONFIG_PATH.read_text())["classifier_crop_box"])
except FileNotFoundError:
    print(f"Can't find {CAMERA_CONFIG_PATH} - is the S: drive mapped and connected?")
    sys.exit(1)


def load_taxonomy_map() -> dict:
    """Maps 'genus species' (lowercase) -> (class, order, family) using
    SpeciesNet's own bundled taxonomy reference file. Lets us check whether
    AIY's species genuinely belongs to whatever higher-level taxon
    SpeciesNet names when it rolls up instead of committing to a species -
    e.g. AIY says California Scrub-Jay, SpeciesNet says only "corvidae
    family" - those aren't actually disagreeing, Corvidae IS the Scrub-Jay's
    real family, SpeciesNet just didn't have enough to go to species level.

    Globs for taxonomy_release*.txt rather than hardcoding the exact
    date-stamped filename, since that'll change with future model versions
    and this should keep working without an edit when it does."""
    import glob
    base = os.path.expanduser(r"~\.cache\kagglehub\models\google\speciesnet")
    matches = glob.glob(os.path.join(base, "**", "taxonomy_release*.txt"), recursive=True)
    if not matches:
        print("Warning: no SpeciesNet taxonomy_release file found - "
              "higher-level agreement checking will be skipped.")
        return {}
    taxonomy_map = {}
    with open(matches[0], encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split(";")
            if len(parts) != 7:
                continue
            _, cls, order, family, genus, species, _ = parts
            if genus and species:
                taxonomy_map[f"{genus.lower()} {species.lower()}"] = (cls, order, family)
    return taxonomy_map


TAXONOMY_MAP = load_taxonomy_map()

# --- AIY on the detector crop (2026-09-23) ---------------------------------
# Same model birdapp's container runs, but fed SpeciesNet's bird bounding box
# (plus margin, letterboxed to square) instead of the full frame. Downloaded
# next to this script on first run from the same URLs as birdapp's Dockerfile.
_HERE = Path(__file__).parent
AIY_MODEL = _HERE / "aiy_birds_v1.tflite"
AIY_LABELS = _HERE / "aiy_labelmap.csv"
_aiy = {}


def aiy_classify(img) -> tuple[str, float]:
    import csv, urllib.request
    import numpy as np
    from PIL import Image
    if not _aiy:
        from ai_edge_litert.interpreter import Interpreter
        if not AIY_MODEL.exists():
            urllib.request.urlretrieve("https://tfhub.dev/google/lite-model/aiy/vision/classifier/birds_V1/3?lite-format=tflite", AIY_MODEL)
        if not AIY_LABELS.exists():
            urllib.request.urlretrieve("https://www.gstatic.com/aihub/tfhub/labelmaps/aiy_birds_V1_labelmap.csv", AIY_LABELS)
        with open(AIY_LABELS) as f:
            _aiy["labels"] = {int(r["id"]): r["name"] for r in csv.DictReader(f)}
        interp = Interpreter(model_path=str(AIY_MODEL))
        interp.allocate_tensors()
        _aiy.update(interp=interp, inp=interp.get_input_details()[0], out=interp.get_output_details()[0])
    w, h = img.size
    side = max(w, h)
    pad = Image.new("RGB", (side, side), (0, 0, 0))
    pad.paste(img, ((side - w) // 2, (side - h) // 2))
    arr = np.expand_dims(np.array(pad.resize((224, 224))), 0).astype(np.uint8)
    interp = _aiy["interp"]
    interp.set_tensor(_aiy["inp"]["index"], arr)
    interp.invoke()
    scores = interp.get_tensor(_aiy["out"]["index"])[0].astype(np.float32) * _aiy["out"]["quantization"][0]
    top = int(np.argmax(scores))
    return _aiy["labels"].get(top, str(top)), float(scores[top])


def aiy_on_detection(image_path: Path, pred: dict) -> tuple[str | None, float | None]:
    """Crop SpeciesNet's top detection (+15% margin) and run AIY on it.
    Returns (None, None) when there's no detection to crop."""
    from PIL import Image
    dets = pred.get("detections") or []
    if not dets:
        return None, None
    x, y, w, h = dets[0]["bbox"]
    mx, my = w * 0.15, h * 0.15
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        W, H = img.size
        crop = img.crop((max(0, int((x - mx) * W)), max(0, int((y - my) * H)),
                         min(W, int((x + w + mx) * W)), min(H, int((y + h + my) * H))))
        return aiy_classify(crop)


def check_higher_level_match(species_aiy: str, family: str, order: str, cls: str) -> bool | None:
    """Whether AIY's species genuinely belongs to whichever higher taxon
    SpeciesNet named - checked family first (most specific), then order,
    then class, since those are the priority order SpeciesNet itself rolls
    up through. Returns None (not False) when there's nothing taxonomic to
    compare - a bare 'bird'/'animal'/'vehicle'/'blank'/'no cv result' result,
    or an AIY species that isn't in SpeciesNet's own taxonomy at all - so
    the caller can tell "genuinely inconclusive" apart from "checked and it
    didn't match"."""
    if not species_aiy:
        return None
    ancestry = TAXONOMY_MAP.get(species_aiy.lower())
    if not ancestry:
        return None
    aiy_class, aiy_order, aiy_family = ancestry
    if family:
        return aiy_family.lower() == family.lower()
    if order:
        return aiy_order.lower() == order.lower()
    if cls:
        return aiy_class.lower() == cls.lower()
    return None


def fetch_queue(limit: int) -> list[dict]:
    resp = requests.get(
        f"{BIRDAPP_BASE_URL}/api/sightings",
        # review_status=pending_review matters here, not just species_id_status
        # =queued: rejecting a photo only sets review_status, it never touches
        # species_id_status, and /api/sightings' default filter (is_trashed=0)
        # doesn't exclude rejected rows either (known legacy quirk - rejection
        # never sets is_trashed=1). Without this, a rejected-but-still-queued
        # photo gets classified anyway, wasting a real inference call on
        # something already in the trash.
        params={"species_id_status": "queued", "review_status": "pending_review", "limit": limit},
        auth=(ADMIN_USER, ADMIN_PASS),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["items"]


def download_image(filename: str, dest_dir: Path) -> Path:
    resp = requests.get(
        f"{BIRDAPP_BASE_URL}/images/{filename}",
        auth=(ADMIN_USER, ADMIN_PASS),
        timeout=15,
    )
    resp.raise_for_status()
    dest = dest_dir / filename
    dest.write_bytes(resp.content)
    crop_to_classifier_box(dest)
    return dest


def crop_to_classifier_box(image_path: Path):
    """/images/{filename} serves the full uncropped original -
    house/garage/driveway/street included. AIY never sees any of that; it
    only ever sees CLASSIFIER_CROP_BOX (see main.py). Without this,
    SpeciesNet's detector was finding parked cars in the background and
    confidently reporting 'vehicle' - not a bug, just a much wider field of
    view than the comparison assumed. Crops and overwrites in place."""
    from PIL import Image
    with Image.open(image_path) as img:
        img.crop(CLASSIFIER_CROP_BOX).save(image_path)


def run_speciesnet(image_dir: Path, predictions_path: Path):
    subprocess.run(
        [
            VENV_PYTHON, "-m", "speciesnet.scripts.run_model",
            "--folders", str(image_dir),
            "--predictions_json", str(predictions_path),
            # Without a location the geofence has nothing to check against, so
            # out-of-region species could pass through (2026-09-24).
            "--country", "USA", "--admin1_region", "CA",
        ],
        check=True,
    )


def parse_prediction(pred: dict) -> dict:
    """SpeciesNet's 'prediction' field is a semicolon-delimited taxonomy
    string: uuid;class;order;family;genus;species;common_name. When
    prediction_source is exactly 'classifier' (not '...+rollup_to_X' or
    'detector'), fields [4]/[5] give a real genus/species - build a
    scientific binomial in the same 'Genus species' format species_aiy
    already uses, so the two can actually be compared meaningfully instead
    of comparing a Latin binomial to a plain-English rollup label like
    'bird' or 'corvidae family' (which is what happened before this fix -
    see PROJECT_MASTER_MAP, every result came back 'disagreed' regardless
    of whether the classifiers actually agreed).

    Falls back to the trailing common-name/rollup label when SpeciesNet
    didn't resolve to species level - that's a meaningful, honest outcome
    to show a human reviewer, not an error to hide.

    Also keeps class/order/family regardless of resolution level, even for
    a rollup - those get thrown away by earlier versions of this function,
    which is exactly what made "corvidae family" impossible to recognize as
    genuine partial agreement with a specific AIY jay species."""
    parts = pred["prediction"].split(";")
    cls, order, family, genus, species = (parts + [""] * 7)[1:6]
    cls = cls if cls not in ("", "no cv result") else None
    order = order if order not in ("", "no cv result") else None
    family = family if family not in ("", "no cv result") else None
    is_species_level = (
        pred.get("prediction_source") == "classifier"
        and genus not in ("", "no cv result")
        and species not in ("", "no cv result")
    )
    if is_species_level:
        label = f"{genus.capitalize()} {species}"
    else:
        label_parts = [p for p in parts if p]
        label = label_parts[-1] if label_parts else "no cv result"

    # When the official prediction rolled up to a coarser label, the raw
    # pre-rollup classifier output may still hold a genuine species-level
    # guess - discovered 2026-09-20 that a Scrub-Jay photo rolled up to
    # official 'bird' at 0.944 while the raw top candidate was correctly
    # 'California Scrub-Jay' at 0.52, matching AIY's own independent guess.
    # Surface that instead of silently discarding it - see birdapp's
    # migrate_v5_to_v6 for the schema this feeds. Only computed when it
    # would add information beyond species_inat itself (i.e. something
    # actually rolled up).
    raw_guess = None
    raw_score = None
    if not is_species_level:
        classifications = pred.get("classifications") or {}
        top_classes = classifications.get("classes") or []
        top_scores = classifications.get("scores") or []
        if top_classes and top_scores:
            top_parts = top_classes[0].split(";")
            top_genus, top_species = (top_parts + [""] * 7)[4:6]
            if top_genus not in ("", "no cv result") and top_species not in ("", "no cv result"):
                raw_guess = f"{top_genus.capitalize()} {top_species}"
                raw_score = top_scores[0]

    return {
        "species_inat": label,
        "confidence_inat": pred["prediction_score"],
        "is_species_level": is_species_level,
        "class": cls,
        "order": order,
        "family": family,
        "species_inat_raw_guess": raw_guess,
        "confidence_inat_raw": raw_score,
    }


def post_second_opinion(sighting_id: int, species_inat: str, confidence_inat: float,
                         is_species_level: bool, higher_level_match: bool | None,
                         species_inat_raw_guess: str | None = None,
                         confidence_inat_raw: float | None = None,
                         species_aiy: str | None = None,
                         confidence_aiy: float | None = None):
    resp = requests.post(
        f"{BIRDAPP_BASE_URL}/api/sightings/{sighting_id}/second-opinion",
        json={
            "species_inat": species_inat,
            "confidence_inat": confidence_inat,
            "is_species_level_inat": is_species_level,
            "higher_level_match": higher_level_match,
            "species_inat_raw_guess": species_inat_raw_guess,
            "confidence_inat_raw": confidence_inat_raw,
            "species_aiy": species_aiy,
            "confidence_aiy": confidence_aiy,
        },
        auth=(ADMIN_USER, ADMIN_PASS),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if not ADMIN_USER or not ADMIN_PASS:
        print(f"No credentials found in {BIRDAPP_ENV_PATH}. Add API_USERNAME "
              "and API_PASSWORD (or ADMIN_USERNAME/ADMIN_PASSWORD) there first.")
        sys.exit(1)

    print(f"Fetching up to {args.limit} queued sightings from {BIRDAPP_BASE_URL} ...")
    queue = fetch_queue(args.limit)
    if not queue:
        print("Queue is empty. Nothing to do.")
        return
    print(f"Got {len(queue)} sightings.")

    with tempfile.TemporaryDirectory(prefix="speciesnet_batch_") as tmp:
        tmp_path = Path(tmp)
        sighting_by_filename = {}
        for s in queue:
            local_path = download_image(s["filename"], tmp_path)
            sighting_by_filename[local_path.name] = s

        predictions_path = tmp_path / "predictions.json"
        print("Running SpeciesNet (a few seconds per photo on CPU) ...")
        run_speciesnet(tmp_path, predictions_path)
        data = json.loads(predictions_path.read_text())

        posted = 0
        for pred in data["predictions"]:
            filename = Path(pred["filepath"]).name
            sighting = sighting_by_filename.get(filename)
            if sighting is None:
                print(f"  ! couldn't match {filename} back to a sighting id, skipping")
                continue
            sighting_id = sighting["id"]
            parsed = parse_prediction(pred)
            aiy_species, aiy_conf = aiy_on_detection(tmp_path / filename, pred)
            higher_level_match = None
            if not parsed["is_species_level"]:
                higher_level_match = check_higher_level_match(
                    aiy_species or sighting.get("species_aiy"), parsed["family"], parsed["order"], parsed["class"]
                )
            result = post_second_opinion(
                sighting_id, parsed["species_inat"], parsed["confidence_inat"],
                parsed["is_species_level"], higher_level_match,
                parsed["species_inat_raw_guess"], parsed["confidence_inat_raw"],
                aiy_species, aiy_conf
            )
            raw_note = ""
            if parsed["species_inat_raw_guess"]:
                raw_note = (f" (raw top guess: {parsed['species_inat_raw_guess']} "
                            f"@ {parsed['confidence_inat_raw']:.2f})")
            aiy_note = f" aiy_crop={aiy_species} ({aiy_conf:.2f})" if aiy_species else " aiy_crop=no detection"
            print(f"  id={sighting_id} -> {parsed['species_inat']} ({parsed['confidence_inat']:.2f}) "
                  f"species_level={parsed['is_species_level']} higher_level_match={higher_level_match} "
                  f"agreement={result.get('classifier_agreement')}{raw_note}{aiy_note}")
            posted += 1

    print(f"Done. Posted {posted} second opinions.")


if __name__ == "__main__":
    main()
