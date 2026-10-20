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
   blank - they were only for the retired SpeciesNet script.
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

## 2. Bird detector (built in)

Nothing to set up separately - MegaDetector runs inside the birdapp
container. The first `docker compose up -d --build` downloads PyTorch
(CPU-only) and the 281 MB MegaDetector weights, so it takes a while and the
image is ~1.5 GB bigger than before; the build fails loudly if the weights
download is incomplete or wrong (checksum), rather than starting broken.

- Check `/stats` -> "Bird detector": it should say *Running*. After the
  first start, every existing photo is re-scanned in the background, newest
  first; the backlog and time per photo are shown there.
- Tuning lives in the `detector` section of `camera_config.json`. That
  file is baked into the image (only `./data` is a live volume), so a change
  takes effect after a rebuild.
  - `count_threshold` (default 0.2): detector confidence at which something
    counts as a bird.
  - `torch_threads` (default 2): CPU threads. More = faster scans, less
    headroom for everything else on the machine.
  - `enabled: false` turns the detector off entirely (photos then stay
    "Not scanned yet" in Manage).

The old laptop SpeciesNet script was retired on 2026-10-20 and lives in
`_Archive/speciesnet-runner/` for reference only. `API_USERNAME` /
`API_PASSWORD` in `.env` are no longer needed by anything in this repo.
