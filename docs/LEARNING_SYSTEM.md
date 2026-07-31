# AutoDevelop AI Personalized Learning

## Purpose

The Phase 4 learning system records explicit feedback about AutoDevelop AI
edits and retrieves similar prior corrections as optional context for future
Develop requests. It is retrieval-augmented personalization, not model
training or fine-tuning.

The system never monitors Lightroom slider changes automatically. Feedback is
captured only when the user invokes **Capture Editing Feedback**.

## Baseline and feedback

A recommendation is the validated setting set returned by the backend. The
baseline is the Lightroom develop state immediately after those settings were
successfully applied. Final settings are the current state when feedback is
captured.

The backend computes each supported feedback delta as:

```text
final setting - applied baseline setting
```

It never compares final settings directly with the pre-AI state. Changes below
the built-in per-setting thresholds are retained in the full delta but excluded
from the significant delta. A sample with no significant change is recorded as
an explicit accepted-without-change signal.

Composition-crop deltas and rotational-leveling deltas are stored, retrieved,
and aggregated as separate behavioral signals. Crop-bound changes never become
leveling preferences, and `CropAngle` changes never become composition-crop
preferences. Both can be significant in the same feedback event. Signed deltas
use the dedicated learning schema rather than absolute DevelopSettings
validation. AI Denoise is not applied or learned as a develop slider.

Transform Upright and HDR Edit Mode are categorical signals rather than numeric
sliders. Baselines carry original, recommended, and applied mode state in
dedicated mode objects; final feedback carries the current modes. A change to
only Upright or only HDR is significant even when every numeric setting is
unchanged. Stable internal photo keys remain separate from display filenames.

## Typical workflow

1. Run **Auto Develop Selected Photos**.
2. Confirm and apply the validated recommendation.
3. Adjust the image manually in Lightroom.
4. Select the photo.
5. Run **AutoDevelop AI → Capture Editing Feedback**.
6. Review the aggregate confirmation and save the feedback.
7. After enough similar examples exist, future Develop requests may include
   aggregate personalized context.

The feedback command reads develop settings but never changes them. It first
asks the backend for a read-only comparison preview and shows that result before
saving. A preview or save failure leaves the local pending session intact so it
can be retried. Successful feedback removes only the corresponding local pending
entry.

## Storage and migrations

The default local database is:

```text
data/autodevelop_learning.sqlite3
```

Relative overrides are resolved from the AutoDevelop AI application root, not
the current working directory:

```yaml
learning:
  database_path: D:\PrivateData\autodevelop_learning.sqlite3
```

SQLite uses WAL mode, foreign keys, bounded busy waits, short-lived
connections, and explicit write transactions. A version table records applied
migrations. Older supported databases migrate during startup. A database with
an unknown future schema fails learning initialization clearly without exposing
its path through the API.

Schema version 2 moves any historical `CropAngle` value out of stored crop
delta JSON and into a dedicated leveling-delta field. Existing sessions and
feedback rows are retained.

Schema versions 3 and 4 add nullable Upright/HDR baseline, recommendation,
final, changed, and accepted fields. Schema version 5 adds nullable HDR
calibration diagnostics, including scene evidence, model confidence, final
decision, contraindications, and learning support. Missing historical values
remain null; migrations never invent mode decisions for old sessions.

For a consistent backup, stop the backend and copy the database together with
any `-wal` and `-shm` files, or use SQLite's backup tooling.

## Stored information

The database stores:

- opaque SHA-256 photo keys;
- Lightroom local identifiers when available;
- filenames for local auditability;
- style and model identifiers;
- original changed settings, recommendation, applied baseline, final settings,
  and computed deltas;
- original, recommended, applied, and final Upright/HDR mode state;
- HDR evidence, confidence, decision-basis, and contraindication diagnostics;
- bounded camera, lens, exposure, dimension, and scene context;
- validation counts and states;
- normalized local visual feature vectors;
- timestamps and schema versions.

It does not store:

- API keys, authorization headers, or provider headers;
- complete raw model responses or prompts;
- image previews, original image files, or base64 image content;
- exact GPS coordinates;
- face embeddings, face recognition, or person identities;
- photo metadata unrelated to editing.

No learning data is uploaded or synchronized to a cloud service.

## Visual features and retrieval

The production MVP representation is a deterministic local color histogram and
luminance-grid descriptor computed from the preview already used for Develop.
It is finite, bounded to 64 dimensions, and L2-normalized. The preview is not
stored. If the local image feature provider is unavailable, baseline and
feedback storage continue and retrieval can use bounded photographic metadata.

Slider, composition-crop, rotational-leveling, and Upright retrieval considers
only usable feedback from the same effective style profile. HDR retrieval uses
usable HDR feedback globally because HDR is determined by current scene need,
not by style. Both paths rank compatible visual features by cosine similarity,
use metadata as a secondary signal, and use recency only to break ties. The
default limits are:

- minimum samples: `3`;
- maximum returned examples: `5`;
- minimum visual similarity: `0.70`;
- maximum candidate pool: `100`.

Retrieved records are aggregated with a similarity-weighted median.
Per-setting caps bound every aggregate, and accepted-without-change samples
contribute zero corrections. Raw historical records, filenames, paths, session
IDs, embeddings, and individual similarity scores never enter the prompt.

The aggregate prompt block is soft context only. Tonal/color, composition-crop,
rotational-leveling, Upright, and HDR observations remain separate. Current
scene evidence, the effective style, provider response validation, application
preferences, and SafetyValidator remain authoritative. HDR learning supplies a
bounded enable-rate signal; it cannot bypass RAW, capability, workflow,
dynamic-range, noise, or exposure safeguards.

## Configuration

Model, provider, and learning behavior is configured through YAML.
Environment variables remain supported for secrets and existing
application/runtime settings such as port and log paths.

```yaml
learning:
  enabled: true
  database_path: data/autodevelop_learning.sqlite3
  minimum_samples: 3
  maximum_results: 5
  minimum_similarity: 0.70
  maximum_candidate_pool: 100
```

Legacy `AUTODEVELOP_LEARNING_*` variables are ignored. YAML is loaded once at
startup, so configuration changes require a backend restart. There is no
automatic reload.

The Lightroom Plug-in Manager also controls whether a run requests
personalization, whether a baseline is recorded after application, and whether
learning details appear in the completion summary. Lightroom controls do not
change backend database configuration.

## Status and reset

Safe aggregate status:

```text
GET /autodevelop/v1/learning/status
```

Status distinguishes total feedback from usable feedback and reports Upright
and HDR usable, changed, and accepted counts independently. A usable sample has
a complete trusted baseline and successfully captured feedback. A changed mode
means the final mode differs from the applied AI mode; an accepted mode means it
was left unchanged.

Exclude one session:

```text
DELETE /autodevelop/v1/learning/sessions/{session_id}
```

Delete all learning rows:

```http
DELETE /autodevelop/v1/learning/all
Content-Type: application/json

{"confirm":"DELETE_ALL_LEARNING_DATA"}
```

The confirmation token must match exactly. These operations affect only the
learning database; they never delete photos, sidecars, catalogs, or Lightroom
metadata.
