# Upright Transform and HDR Support

AutoDevelop AI treats Lightroom Transform Upright and HDR Edit Mode as
independent categorical decisions. Neither feature is modeled as a numeric
Develop slider.

## Lightroom SDK fields

The Lightroom Classic SDK exposes both values through
`photo:getDevelopSettings()` and accepts them through
`photo:applyDevelopSettings()`:

| Feature | Lightroom field | Values |
|---|---|---|
| Transform Upright | `PerspectiveUpright` | `0` Off, `1` Auto, `2` Full, `3` Level, `4` Vertical |
| HDR Edit Mode | `HDREditMode` | `0` Off, `1` On |

`EnableTransform=true` is written with an active Upright recommendation.
Lightroom owns any generated `UprightTransform_0` through
`UprightTransform_5` matrices; AutoDevelop AI neither recommends, stores, nor
writes those matrices.

`HDRMaxValue` is captured as diagnostic baseline data. It is not currently a
learned preference.

## Geometry separation

The three geometry decisions remain distinct:

- Composition crop writes `CropLeft`, `CropRight`, `CropTop`, and
  `CropBottom`.
- Rotational leveling writes `CropAngle`.
- Transform Upright writes `EnableTransform` and `PerspectiveUpright`.

Upright Level is not a substitute for rotational leveling, and `CropAngle` is
never used to simulate an Upright mode.

Guided Upright is unsupported because the verified probe did not cover it and
the plug-in has no user-defined guide coordinates. Unknown Lightroom numeric
values are preserved as unsupported diagnostic values and are never guessed
as Off.

## Recommendation and validation

Successful Develop responses always contain `upright` and `enable_hdr`
objects. Upright defaults to inactive mode `off`. HDR defaults to
`enabled=false`, but a model-supplied Off confidence and reason are retained
for audit; confidence is zero only when no assessment was supplied.

Scene analysis now runs before every Develop request, including manually
selected profiles. It supplies semantic geometry and dynamic-range evidence
to the final Develop stage. HDR is evaluated as a natural quality-enhancement
option for moderate-to-very-high range RAW scenes, not only as rescue for
catastrophic clipping.

The deterministic evidence score includes dynamic-range strength, highlight
and shadow pressure, backlighting, bright-sky/dark-foreground and
bright-window/dark-interior cues, sunrise/sunset, and a bounded learned
preference bonus. Learning and user preference bonuses are applied only when
visual evidence exists. HDR has no style-profile permission or profile-specific
confidence threshold.

HDR can be enabled through one of three deterministic paths:

1. **Model recommendation:** the scene is an HDR candidate, combined evidence
   is at least `0.40`, and model confidence is at least `0.65`.
2. **Objective evidence:** the scene is an HDR candidate and base scene
   evidence is at least `0.65`, even if the model did not recommend HDR.
3. **Learned preference:** Prefer HDR is selected, at least the configured
   minimum number of similar global HDR samples support an enable rate of at
   least `0.70`, base evidence is at least `0.18`, and combined evidence is at
   least `0.36`.

Every path requires a RAW source, caller HDR capability, a non-SDR-only
workflow, moderate-or-higher dynamic range, and no severe-underexposure or
high-noise contraindication. Scene inconsistency also disables HDR.

The Develop stage selects categorical recommendations, and safety validation
then independently enforces:

- the selected profile's allowed Upright modes and minimum Upright confidence;
- inactive Upright normalization to Off;
- strict rejection of unknown or Guided Upright values;
- HDR scene evidence, caller capability, and workflow safeguards;
- inactive HDR normalization to disabled.

Crop and rotational-leveling rejection diagnostics are not reused for
Upright. Develop completion logs include scene candidacy, scene confidence,
evidence score, learning rate and sample count, raw recommendation/confidence,
validated state/confidence, rejection flag, and a stable Off reason.

The Lightroom preference offers Conservative, Balanced, and Prefer HDR.
Conservative suppresses the learned HDR bonus. Balanced uses current scene,
model, and eligible learning evidence without a user bonus. Prefer HDR adds a
bounded `0.08` evidence bonus and permits the learned-preference path. It never
bypasses RAW eligibility, scene evidence, caller capability, workflow, noise,
exposure, or safety validation.

## Lightroom application verification

The diagnostic plug-in under `tools/LightroomDevelopSettingsProbe.lrplugin`
uses a two-stage workflow: apply and read back, allow visual inspection in
Develop, then record the verdict and restore.

On 2026-07-30, using `DSC_7957.NEF`, Lightroom successfully applied, displayed,
read back, and restored:

- Upright Auto (`1`)
- Upright Full (`2`)
- Upright Level (`3`)
- Upright Vertical (`4`)
- HDR Off (`0`)
- HDR On (`1`)

The earlier single-modal test was discarded because it could not reliably
support Develop-module UI inspection. The two-stage results are the production
application gate.

All metadata capture and confirmation rendering occur outside catalog write
access. The existing write transaction owns both application and failure
restoration.

## Learning

Baseline capture records:

- original, recommended, and applied Upright mode;
- original, recommended, and applied HDR state;
- raw `PerspectiveUpright` and `HDREditMode` values;
- diagnostic `HDRMaxValue`.

Numeric Develop settings and categorical modes use separate transport fields.
The Lightroom plug-in captures the post-apply state once, outside catalog write
access, then stores a pending session. Empty HDR contraindication lists are
omitted at the Lua JSON boundary and restored by the backend schema as `[]`.
The repository reads stored contraindications as arrays, not setting objects.

Feedback compares final modes exactly. A feedback session is significant when
only Upright or only HDR changes, even if no slider, crop, or rotation changes.
Schema migrations 3 and 4 add nullable baseline, AI, final, changed, and
accepted columns. Migration 5 adds nullable HDR calibration columns for scene
candidacy/confidence, evidence score, raw and validated recommendation
confidence, rejection reason, personalization use, and learned enable rate.
Existing rows remain readable and are not populated with invented values.

Personalization aggregates modes independently from slider corrections. It
requires at least three similar usable examples and a weighted consensus
before exposing a soft preference. Slider, crop, rotational-leveling, and
Upright retrieval remains scoped to the effective style. HDR retrieval is
global across profiles and supplies a weighted enable rate because HDR is based
on scene need rather than visual style. Learning never overrides Upright
profile policy or HDR scene, confidence, source-format, workflow, and caller
capability checks.

Feedback capture first requests a read-only comparison preview. Preview and
save use the trusted stored baseline; a failure leaves the pending session
available for retry.

Learning status reports usable sample, change, and acceptance counts
independently for Upright and HDR.
