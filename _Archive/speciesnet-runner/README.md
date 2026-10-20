# Retired 2026-10-20

`run_second_opinion.py` ran SpeciesNet on a laptop as a second opinion and
posted results to `/api/sightings/{id}/second-opinion`. It was replaced by
the in-container MegaDetector worker (`detector.py`) - see HISTORY.md,
"Retiring SpeciesNet", for the numbers behind that decision.

Kept for reference only. Don't run it: the endpoint still accepts its
results, but it would overwrite the per-bird AIY guess with its own
single-bird one.
