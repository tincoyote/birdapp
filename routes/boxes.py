"""Shared browser code for drawing MegaDetector boxes over a photo.

Used by Manage, Species Queue and Gallery lightboxes (2026-10-20). Each page
inserts BOXES_CSS into its <style> and BOXES_JS into its <script>, then wraps
the lightbox <img> in <div class="bx-wrap"> and calls
    drawBoxes(imgElement, sighting.detections)
after setting the image src. Boxes are positioned in % of the image, so
they stay aligned at any display size without re-measuring.

Counted detections (an animal at or above count_threshold) get a numbered
solid box; weaker "maybe" detections a faint dashed one; people/vehicles an
orange box. Numbers match the per-bird list in the Species Queue panel.
"""

BOXES_CSS = r"""
.bx-wrap { position: relative; display: inline-block; line-height: 0; max-width: 80%; }
.bx-wrap img { max-width: 100%; max-height: 65vh; display: block; }
.bx { position: absolute; border: 2px solid #2ecc71; border-radius: 2px; pointer-events: none; box-sizing: border-box; }
.bx.weak { border: 1px dashed rgba(255,255,255,0.55); }
.bx.other { border-color: #ff9800; }
.bx-tag { position: absolute; left: -2px; top: -18px; background: #2ecc71; color: #000; font: 600 11px/16px sans-serif; padding: 0 4px; border-radius: 2px; white-space: nowrap; }
.bx.other .bx-tag { background: #ff9800; }
.bx.weak .bx-tag { display: none; }
.bx-toggle { font-size: 12px; color: #ccc; margin-top: 6px; cursor: pointer; user-select: none; }
"""

BOXES_JS = r"""
let boxesVisible = true;
function birdName(d) {
    // Per-bird display name: human-confirmed, else AIY's guess on the crop
    if (d.species_confirmed) return d.species_confirmed;
    if (d.common_name) return d.common_name;
    return d.species_aiy || 'unknown';
}
function countedBirds(s) {
    return (s.detections || []).filter(d => d.counted && d.species_confirmed !== '__ignore__');
}
function birdSummary(s) {
    // "2x House Finch, California Scrub-Jay" - groups identical names
    const counts = {};
    countedBirds(s).forEach(d => { const n = birdName(d); counts[n] = (counts[n] || 0) + 1; });
    return Object.entries(counts).map(([n, c]) => (c > 1 ? c + 'x ' : '') + n).join(', ');
}
function drawBoxes(img, detections) {
    const wrap = img.parentElement;
    wrap.querySelectorAll('.bx').forEach(el => el.remove());
    if (!boxesVisible) return;
    let n = 0;
    (detections || []).forEach(d => {
        const el = document.createElement('div');
        const counted = d.counted && d.species_confirmed !== '__ignore__';
        el.className = 'bx' + (d.category !== 'animal' ? ' other' : (counted ? '' : ' weak'));
        el.style.left = (d.x * 100) + '%';
        el.style.top = (d.y * 100) + '%';
        el.style.width = (d.w * 100) + '%';
        el.style.height = (d.h * 100) + '%';
        const tag = document.createElement('span');
        tag.className = 'bx-tag';
        if (d.category === 'animal') {
            tag.textContent = counted ? `${++n} ${Math.round(d.det_conf * 100)}%` : '';
        } else {
            tag.textContent = `${d.category} ${Math.round(d.det_conf * 100)}%`;
        }
        el.title = birdName(d);
        el.appendChild(tag);
        wrap.appendChild(el);
    });
}
function toggleBoxes(img, detections) {
    boxesVisible = !boxesVisible;
    drawBoxes(img, detections);
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
