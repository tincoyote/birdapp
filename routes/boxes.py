"""Shared browser code for drawing MegaDetector boxes over a photo.

Used by Manage, Species Queue and Gallery lightboxes (2026-10-20). Each page
inserts BOXES_CSS into its <style> and BOXES_JS into its <script>, then wraps
the lightbox <img> in <div class="bx-wrap"> and calls
    drawBoxes(imgElement, sighting, {pct: 'det' | 'aiy', onClick: fn})
after setting the image src. Boxes are positioned in % of the image, so
they stay aligned at any display size without re-measuring.

Listed detections (at or above count_threshold) get a numbered box: green
for animals, orange for people/vehicles, grey dashed once a human has
excluded it. Weaker "maybe" detections get a faint unnumbered outline.
Numbers match the per-box rows in the Species Queue panel.
"""

BOXES_CSS = r"""
.bx-wrap { position: relative; display: inline-block; line-height: 0; max-width: 80%; }
.bx-wrap img { max-width: 100%; max-height: 65vh; display: block; }
.bx { position: absolute; border: 2px solid #2ecc71; border-radius: 2px; pointer-events: none; box-sizing: border-box; }
.bx.click { pointer-events: auto; cursor: pointer; }
.bx.click:hover { box-shadow: 0 0 0 2px rgba(255,255,255,0.6); }
.bx.weak { border: 1px dashed rgba(255,255,255,0.55); }
.bx.other { border-color: #ff9800; }
.bx.excluded { border: 2px dashed #888; background: rgba(0,0,0,0.35); }
.bx-tag { position: absolute; left: -2px; top: -18px; background: #2ecc71; color: #000; font: 600 11px/16px sans-serif; padding: 0 4px; border-radius: 2px; white-space: nowrap; }
.bx.other .bx-tag { background: #ff9800; }
.bx.excluded .bx-tag { background: #888; color: #fff; }
.bx.weak .bx-tag { display: none; }
.bx-toggle { font-size: 12px; color: #ccc; margin-top: 6px; cursor: pointer; user-select: none; }
"""

BOXES_JS = r"""
let boxesVisible = true;
function birdName(d) {
    // Per-bird display name: human-confirmed, else AIY's guess on the crop
    if (d.species_confirmed && !d.excluded) return d.species_confirmed;
    if (d.common_name) return d.common_name;
    return d.species_aiy || 'unknown';
}
function countedBirds(s) { return (s.detections || []).filter(d => d.counted); }
function listedBoxes(s) { return (s.detections || []).filter(d => d.listed); }
function boxNumber(s, d) { return listedBoxes(s).indexOf(d) + 1; }
function birdSummary(s) {
    // "2x House Finch, California Scrub-Jay" - groups identical names
    const counts = {};
    countedBirds(s).forEach(d => { const n = birdName(d); counts[n] = (counts[n] || 0) + 1; });
    return Object.entries(counts).map(([n, c]) => (c > 1 ? c + 'x ' : '') + n).join(', ');
}
function pctText(v) { return v == null ? '' : Math.round(v * 100) + '%'; }

// drawBoxes(img, sighting, opts)
//   opts.pct: 'det' (detector confidence - Manage) or 'aiy' (species
//             confidence - Species Queue, Gallery, Trash). People/vehicles
//             have no species, so they always show the detector's %.
//   opts.onClick(detection): if given, listed boxes are clickable
//             (used to exclude / re-include a box).
// Every listed box (at or above the threshold, any category) is numbered
// in the same order as the per-box rows in Species Queue.
function drawBoxes(img, s, opts) {
    opts = opts || {};
    const wrap = img.parentElement;
    wrap.querySelectorAll('.bx').forEach(el => el.remove());
    if (!boxesVisible || !s) return;
    const listed = listedBoxes(s);
    (s.detections || []).forEach(d => {
        const el = document.createElement('div');
        const isListed = listed.includes(d);
        let cls = 'bx';
        if (!isListed) cls += ' weak';
        else if (d.excluded) cls += ' excluded';
        else if (d.category !== 'animal') cls += ' other';
        if (isListed && opts.onClick) cls += ' click';
        el.className = cls;
        el.style.left = (d.x * 100) + '%';
        el.style.top = (d.y * 100) + '%';
        el.style.width = (d.w * 100) + '%';
        el.style.height = (d.h * 100) + '%';
        if (isListed) {
            const tag = document.createElement('span');
            tag.className = 'bx-tag';
            const n = listed.indexOf(d) + 1;
            const kind = d.category === 'animal' ? '' : ' ' + d.category;
            const pct = (opts.pct === 'aiy' && d.category === 'animal') ? pctText(d.confidence_aiy) : pctText(d.det_conf);
            tag.textContent = d.excluded ? `${n} excluded` : `${n}${kind} ${pct}`;
            el.appendChild(tag);
            el.title = d.excluded ? 'Excluded - click to include again'
                : `${d.category === 'animal' ? birdName(d) : d.category}` + (opts.onClick ? ' - click to exclude' : '');
            if (opts.onClick) el.onclick = (ev) => { ev.stopPropagation(); opts.onClick(d); };
        }
        wrap.appendChild(el);
    });
}
function toggleBoxes(img, s, opts) {
    boxesVisible = !boxesVisible;
    drawBoxes(img, s, opts);
}
// Exclude / re-include one box (saved immediately). Merges the server's
// recomputed counts back into the sighting object and returns it.
async function setExcluded(s, d, excluded) {
    const res = await fetch(`/api/detections/${d.id}/exclude`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ excluded })
    });
    if (!res.ok) return null;
    const upd = await res.json();
    if (upd.error) return null;
    Object.assign(s, upd);
    return s;
}
function detectorBadge(s) {
    // Small status chip for tables/cards
    if (s.detect_status === 'pending') return '<span class="dbadge" style="background:#fff3cd;color:#856404">scanning</span>';
    if (s.detect_status === 'failed') return '<span class="dbadge" style="background:#f8d7da;color:#721c24">scan failed</span>';
    const n = countedBirds(s).length;
    if (!n) return '<span class="dbadge" style="background:#e2e3e5;color:#383d41">no bird</span>';
    return `<span class="dbadge" style="background:#d4edda;color:#155724">${n} bird${n > 1 ? 's' : ''}</span>`;
}
"""

DBADGE_CSS = ".dbadge { display:inline-block; font-size:11px; font-weight:600; padding:2px 7px; border-radius:8px; }"
