# Project History & Lessons Learned

The full story of how this project got to its current state, and the
transferable lessons for anyone attempting something similar. For the
current architecture only, see [README.md](README.md).

## Camera hardware

**Camera #1** (an earlier hardware-hacked camera): TTL/serial access
succeeded, but custom firmware got flashed before backing up the original
stock firmware. Wi-Fi turned out to live on a separate chip, discovered only
*after* flashing broke it. The board didn't survive the resulting debugging.

**Lesson**: back up stock firmware before flashing anything, and understand
a device's actual hardware architecture (which chip does what) before
modifying it - don't assume.

**Camera #2**: solar/battery/boost sizing was undersized for the camera's
boot current spike - the camera would brown out and reboot-loop the moment
it tried to start up, even with an apparently adequate steady-state power
budget. No actively-maintained firmware port existed for that camera model
either, despite otherwise matching requirements.

**Lesson**: boot current spikes matter as much as steady-state draw when
sizing a power system. Verify a firmware port actually exists and is
maintained before committing to specific hardware.

**Wyze Cam v3 + Thingino** is the combination that actually worked, and is
the current hardware.

## Power system

**Original topology** (TP4056 charge-only module + a separate MT3608 boost
converter, both feeding off a raw LiPo tap): failed because the TP4056
**cuts both charge AND load output on any loss of solar input** - not just
on low battery voltage, which was the assumed failure mode. This meant any
cloud, shadow, or nightfall could cut power to the camera entirely,
regardless of remaining battery capacity.

**Lesson**: verify a charger IC's actual behavior on input loss against its
datasheet, don't assume it behaves like a simple pass-through.

**Replacement**: Adafruit bq24074 (proper USB/DC/solar charger with power
path management, so the load is powered independently of charge state) +
Adafruit PowerBoost 500. This is the current architecture.

**Battery deep-discharge saga**: an early battery on the new architecture
was run down to roughly 2.0V under unsupervised load - well below where
most LiPo protection circuits are designed to cut off - and ultimately
declared unrecoverable. Diagnostic findings along the way:
- The bq24074's two LEDs mean different things: **green (Power Good)** only
  confirms valid input voltage; **red (CHG)** is the only indicator that
  confirms current is actually flowing into the battery. Don't conflate them.
- A multimeter reading that lands suspiciously exactly on a documented
  protection-circuit cutoff value (e.g. ~3.0V for many packs) is itself
  diagnostic of a tripped protection circuit, not just "a low but otherwise
  normal" reading.
- A brief red-LED flash-then-off pattern on connection is consistent with
  the charger attempting and aborting a charge cycle against a battery whose
  protection circuit has latched - different from a battery that's simply
  charging slowly.

**Lesson**: don't leave a battery that's already shown warning signs
charging unsupervised for extended periods, and check voltage before and
after any significant power event (this was skipped once during a later
overnight failure, and the missing data point was genuinely missed).

**Pulsing (not solid, not off) red CHG LED**: confirmed via TI's own
documentation to mean a safety timer expired - either the pre-charge timer
before the battery reached a minimum voltage, or the fast-charge timer
before current tapered to the termination threshold. A genuinely different
failure mode from the flash-and-die pattern above, plausibly caused by solar
ripple (clouds, shadows) repeatedly interrupting a charge cycle before it
could complete.

**Hardware mod attempt**: to address suspected ripple-related pulsing,
attempted two documented (verified against Adafruit/TI's own docs before
proceeding, given the irreversibility) modifications: cutting the board's
1.0A charge-current jumper trace and bridging it to 1.5A, and adding a 47µF
capacitor to the board's "Opt. Cap" pads (completing TI's own two-capacitor
reference design). The board did not survive the soldering work. A stock
reserve board was substituted while the mod is reconsidered.

**Lesson**: verify hardware modification instructions against the
manufacturer's own documentation before cutting anything irreversible, and
have a spare board in reserve before attempting an irreversible modification
at all - it directly saved this project from an extended outage.

## Camera framing / crop calibration

Three separate coordinate systems track where the birdbath sits in frame:
the camera's own motion-detection ROI (`prudynt.json`, on the camera itself),
the classifier's crop box (what the AI models actually see), and the public
display crop (what's shown on the family page, deliberately trimmed to
exclude the driveway/street for privacy). These started as three
independently-hardcoded values and were consolidated into one shared,
git-tracked `camera_config.json` for two of the three (the camera's own
motion ROI has to stay separate - it's genuinely a different system,
updated over SSH).

**Lesson**: when multiple coordinate/config values are meant to describe the
"same" physical thing, consolidate them into one shared source of truth
early - before they drift out of sync, not after. Also: non-secret
configuration that changes over a project's life belongs in git-tracked
files, not `.env` - `.env`'s gitignore is exactly right for credentials and
exactly wrong for anything you want change history on.

## Software architecture

**SQLite over a network share is not reliable for anything time-sensitive.**
Reading `birds.db` directly from a mapped network drive produced stale
snapshots that exactly mimicked a real bug - a fix that had actually worked
looked broken for an entire session because the read path, not the fix, was
stale. The only way to tell the difference was checking through a
completely different path (the live API) that couldn't share the same
staleness.

**Lesson**: for anything you need current data on, go through the
application's own API, not a direct file read over a network share - even
for read-only inspection, and especially for verifying a recent write.

**A second process should never write to the primary app's database
directly**, even if file access is technically possible. The second
classifier (SpeciesNet) runs entirely off-box and only ever calls birdapp's
own HTTP API - never opens `birds.db` - keeping the container as the sole
writer, always. This is what made the "stale local read" problem above a
read-side-only issue rather than an actual data-corruption risk.

**A comparison metric that always returns the same result regardless of
input is a red flag, not a null result.** An early version of the two-
classifier agreement check returned "disagreed" on every single result,
which turned out to mean the comparison itself was broken (comparing a
Latin scientific name against a plain-English label, which can never
string-match) - not that the classifiers genuinely never agreed.

**Two classifiers can only meaningfully agree or disagree if they're shown
the same input.** A crop-box mismatch had one classifier seeing the full
uncropped frame (background, driveway, parked cars) while the other only
ever saw a tight crop around the birdbath - producing confident "vehicle"
results that looked like classifier disagreement but were actually a
framing bug.

**A classifier that can honestly decline to commit** (rolling up to a
higher taxonomic level, or an explicit "no result") **is more useful for
human review than one that always guesses a specific answer.** The
second classifier's willingness to say "I'm not sure, but it's in this
family" turned out to carry real information once compared against the
first classifier's specific (sometimes wrong) guess - worth explicitly
checking whether a "vague" answer actually agrees at a higher level before
writing it off as unhelpful.

**A single classifier's own confidence score doesn't reliably separate real
subjects from empty/junk frames.** Measured directly against real review
data: a large fraction of human-approved photos would have been
auto-rejected at a plausible-looking confidence threshold, and a similar
fraction of confidently-labeled photos were actually empty frames. Confirmed
as a real property of the classifier, not a tuning problem to keep
re-litigating.

**Embedding text into inline `onclick="..."` attributes is fragile and
breaks silently.** Any embedded value containing a quote character collides
with the surrounding HTML attribute's own quoting, truncating the handler
into invalid JavaScript with no visible error. Happened twice in this
project - once fixed, then reintroduced during an unrelated rewrite. Use
`data-*` attributes read at click time instead; it isn't vulnerable to this
class of bug at all.

**An idempotency guard needs to match the actual intended workflow
precisely, not just "block anything already touched."** A guard meant to
stop accidental reprocessing of in-flight items also blocked a legitimate,
intentional resend of an already-completed item, because "already touched"
and "shouldn't be touched again" turned out not to be the same condition.
Worth explicitly enumerating which states should and shouldn't allow an
action, rather than defaulting to the broadest-seeming safe rule.

**A database column used as both a display value and a filter/grouping key
breaks the moment those two purposes diverge.** A species filter dropdown
displayed one column's value as the label while filtering on a different
column - safe only as long as the two happened to agree, which stopped
being true once a review workflow existed specifically to *correct*
mismatches between them. The fix: display and filter should always use the
identical computed expression, never two different columns that are assumed
to correspond.

## General

Across all of the above, the recurring pattern worth naming explicitly:
**most of these bugs came from two things that were assumed to correspond
(two classifiers' inputs, two columns' values, a read path and the true
current state, "already touched" and "shouldn't be touched again") quietly
drifting apart.** Verifying that assumption directly - with a real search,
a real data check, or a real test against the actual live path - caught
every one of them faster than reasoning about it in the abstract would have.
