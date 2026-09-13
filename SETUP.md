# Setup

A generic walkthrough for running birdapp somewhere other than the original
deployment. Assumes basic comfort with Docker and the command line, but no
prior familiarity with this specific project.

## 1. Birdapp (the main app)

1. Clone the repo onto whatever machine will run Docker (a NAS, a
   Raspberry Pi, a spare PC - anything that can run Docker Compose):
   `git clone https://github.com/tincoyote/birdapp.git`
2. Copy `.env.example` to `.env` and fill in real values for
   `ADMIN_USERNAME`/`ADMIN_PASSWORD`. Leave `API_USERNAME`/`API_PASSWORD`
   blank unless you're also setting up the SpeciesNet second-opinion script
   below - see `.env.example` for what each one is for.
3. Build and start it: `docker compose up -d --build`
4. Birdapp is now reachable at `http://<your-server>:8000`. `/manage`,
   `/gallery`, `/species-queue`, and `/trash` need the admin credentials
   from step 2; `/family` and `/about` are public.
5. Point your camera's motion-triggered upload feature at
   `http://<your-server>:8000/webhook`. Any camera or system that can POST
   an image works - see the note in README.md about this not being
   Thingino- or Wyze-specific.
6. Recalibrate `camera_config.json` for your own camera's physical framing
   - the shipped values match one particular camera's exact mounting angle
   and won't be right for yours. Take a real photo from your camera, note
   the pixel coordinates of what you want the classifier to see and what
   you want the public gallery to show, and edit the two boxes in that
   file accordingly.

## 2. SpeciesNet second-opinion script (optional)

This is a completely separate piece from birdapp itself - it's a standalone
script that runs on any machine with Python (your own laptop or desktop,
not necessarily the server running birdapp), calls birdapp's API, and never
touches its database directly. Birdapp works fine without this - sightings
just won't get a second classifier opinion, and Species Queue will only
ever show AIY's guess.

**Give it its own folder, separate from the birdapp checkout.** Do not put
it inside your birdapp clone. It needs its own Python virtual environment
with a large, unrelated dependency stack (PyTorch and friends, a few
hundred MB), and mixing that into the birdapp git repo risks accidentally
committing gigabytes of files that have nothing to do with the app itself.

1. Create a new folder anywhere else on your machine, e.g.
   `~/speciesnet-runner/` (unrelated to the repo folder of the same name -
   that one just holds the script for you to copy out).
2. Copy `speciesnet-runner/run_second_opinion.py` from this repo into your
   new folder.
3. Inside that new folder: `python -m venv .venv`, activate it, then
   `pip install speciesnet requests pillow`.
4. **Open the copied script and edit the three constants marked "EDIT
   THESE" near the top** - they need to point at *your* birdapp, not the
   original deployment's:
   - `BIRDAPP_BASE_URL` - wherever your birdapp is actually reachable at
     (e.g. `http://192.168.1.50:8000` if you haven't set up a domain name).
   - `BIRDAPP_ENV_PATH` - the filesystem path to *your* birdapp's `.env`
     file (this script reads credentials from it directly).
   - `CAMERA_CONFIG_PATH` - the filesystem path to *your* birdapp's
     `camera_config.json`.
5. Add `API_USERNAME`/`API_PASSWORD` to birdapp's `.env` if you haven't
   already (step 2 above) - this script authenticates as that account
   rather than needing your personal admin login.
6. Run it whenever you want queued sightings classified:
   `.venv\Scripts\python.exe run_second_opinion.py --limit 50`
   (or `.venv/bin/python` on macOS/Linux). Nothing runs it automatically -
   this is a manual, on-demand step.
