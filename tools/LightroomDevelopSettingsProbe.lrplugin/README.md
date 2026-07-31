# Lightroom Develop Settings Probe

This standalone diagnostic plugin records every key and value returned by
`photo:getDevelopSettings()`. Its explicit application command temporarily
changes and then restores the selected test photo. It does not modify
AutoDevelop AI production behavior or learning data.

## Install

1. Open Lightroom Classic's Plug-in Manager.
2. Choose **Add**.
3. Select `tools/LightroomDevelopSettingsProbe.lrplugin`.
4. Confirm that **AutoDevelop AI Develop Settings Probe** is enabled.

## Capture matrix

Use one RAW photo for every capture. Before each capture, make the stated
Develop change, then choose:

**Library > Plug-in Extras > Dump Develop Settings**

Enter the exact scenario label shown below:

1. `Baseline` — reset the photo, leave Transform/Upright off, and leave HDR off.
2. `Upright Auto` — select Transform > Upright > Auto.
3. `Upright Level` — return to the baseline state, then select Level.
4. `Upright Vertical` — return to the baseline state, then select Vertical.
5. `Upright Full` — return to the baseline state, then select Full.
6. `HDR On` — return to the baseline state, then enable HDR edit mode.
7. `HDR Off` — disable HDR edit mode after the HDR On capture.

Do not make unrelated Develop changes between captures. Returning to the
baseline state before each Upright mode prevents one mode's generated
transforms from affecting another mode's snapshot.

## Output

Snapshots are appended to:

`Documents/AutoDevelopAI-DevelopSettingsProbe.log`

Each snapshot contains the UTC timestamp, Lightroom version, source filename,
scenario label, setting count, and a sorted recursive dump of every returned
key, Lua value type, and value.

After all seven captures, provide the complete log for comparison. The
Transform and HDR support conclusions must be based on these observed values,
not guessed field names or mode mappings.

## Application verification

Use a disposable test RAW or a virtual copy. The probe temporarily changes the
selected mode and then restores the original values.

1. Select the test photo.
2. Choose **Library > Plug-in Extras > Start Upright/HDR Application Test**.
3. Select one operation and dismiss the completion message.
4. Switch to Develop and inspect the Transform or HDR UI without changing the
   selected photo.
5. Return to **Library > Plug-in Extras** and choose
   **Record Upright/HDR Result and Restore**.
6. Record **UI Matches**, **UI Does Not Match**, or **Could Not Verify**.
7. Confirm that the completion dialog reports restore as `true`.
8. Repeat for Upright Off, Auto, Full, Level, Vertical, HDR Off, and HDR On.

The start command refuses to run when it cannot capture values needed to
restore the test photo. It leaves the temporary mode in place so Lightroom can
be inspected without a blocking modal dialog. The result command verifies that
the same photo is selected before restoring it. Metadata reads occur outside
catalog write access. Only `applyDevelopSettings()` runs within write
transactions.

Application results are appended to the same log:

`Documents/AutoDevelopAI-DevelopSettingsProbe.log`

Provide the complete application section after all seven operations. Production
application support must not be enabled unless apply, read-back, UI, and restore
results are confirmed.
