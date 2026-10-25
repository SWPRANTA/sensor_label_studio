# Road Sensor Studio

## Launch

Double-click `run_app.cmd` in this folder, then open http://127.0.0.1:8501 in your browser. The launcher uses the app's separate `.venv` environment. If the app is already running, open the address instead of starting another copy.

Manual launch from this folder:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On another computer, install Python 3.12, create `.venv`, and install `requirements.txt` first. No research-notebook packages are changed.

## Workflow

1. Upload a CSV in the sidebar. For your recordings, use `elapsed_time_ms` with milliseconds. It is divided by 1,000 to match the notebook plots. Epoch timestamps should have the first valid timestamp subtracted.
2. Enter Plot start and Window length in seconds, such as 8. Move with Previous/Next window or select Plot entire recording.
3. Inspect all numeric sensor groups, the original/current labels and motion state. Other text fields are in the read-only sample preview.
4. Set Edit start and Edit end within the plot window, choose a label, then Apply label. Custom labels, Undo and Redo are supported. Large/whole-file edits require confirmation.
5. Click Prepare verified CSV, then Download relabeled CSV. The complete recording is downloaded, not just the displayed portion. An edit log and verification JSON can also be downloaded.

Default intervals are start-inclusive/end-exclusive: `start <= time < end`. The Include end timestamp checkbox explicitly makes the end inclusive. Chart zooming does not redefine the edit bounds. Duplicate timestamps select every matching original sample. Missing timestamps stay in the file but cannot be selected by time; backwards clocks are rejected rather than sorted.

## Data preservation

### Plotting import updates

The app loads its own plotting.py by source version, so a retained older plotting module cannot hide new helpers such as LABEL_COLORS. This refreshes only plotting code, not CSV editor objects or session state. If an older error is still displayed after updating, use Streamlit's Rerun control first, not a browser refresh. Save/download edits before any full browser refresh or server restart.

### Label shading

All sensor plots and the full-recording overview have translucent backgrounds for the current road labels, matching the earlier notebook palette: normal grey, pothole orange, speed breaker green, utility cut purple, uneven manhole pink, and raveling mustard. A color key is shown above the label timeline. Custom labels receive stable colors; uncertain is grey. Shading is computed from the full-resolution current label column, independently of chart preview reduction, and updates after Apply, Undo or Redo. Dashed neutral lines distinguish edit bounds from road-label regions.

Hover over any chart for time and values. Raw-channel tooltips preserve the original CSV cell spelling, including its decimal precision; derived values are computed display-only values. Long previews show values for the retained plotted samples, not interpolated values at every cursor position. Shorter windows or a higher Preview points setting show more original samples.

Rendering compatibility: label bands use the upper SVG layer with explicit panel bounds, avoiding the installed Plotly.js failure for `layer="between"` with `yref="y domain"`. Decorative shapes ignore mouse events so hover and zoom remain available. No chart is rendered as a static image.

Use Streamlit's Rerun control (or press R outside a textbox) to load plotting updates without restarting or browser-refreshing. Existing session edits are retained. Download unsaved edits before any server restart or full browser refresh, which can end the in-memory session.

The app retains the uploaded CSV bytes separately from numeric plotting views. Export replaces only changed label tokens, then verifies every other byte and field is unchanged. Original precision, timestamps, sensor values, row/column order, blanks, numeric spelling, BOM and line endings are preserved. Source files are never overwritten; browser downloads use a separate `_relabeled.csv` name. Derived traces and preview columns are not added to exports.

Long chart previews retain local extrema and missing-value markers for speed. Editing and export always use the full original rows, not preview points. All sensor columns are retained, including magnetic, pressure, illuminance and step count. Derived IMU traces are visual aids, not independent proof of a road anomaly.

**Download frequently and before closing or refreshing the browser. Edits are session-only, not automatically saved to disk.** Multiple open files have separate edits; edits are not synchronized across phones. JSON logs are audit records, not an automatic resume/import format.

Supported CSV settings: UTF-8, Windows-1252 or Latin-1; comma, semicolon or tab. Files need unique nonempty headers and exactly one label column. UTF-16 and malformed/ragged records are rejected. New labels cannot be empty, contain newline/NUL, exceed 160 characters, start with a spreadsheet-formula marker, or be unrepresentable in the original encoding.

The server binds to 127.0.0.1, with a 128 MB upload limit and telemetry disabled. Uploaded data are processed locally. Keep relabeled downloads separate from the original datasets; existing training caches expect original checksums and are not automatically updated by this app.

## Included code and checks

`app.py` is the UI, `csv_document.py` implements byte-preserving edits, and `plotting.py` supplies grouped/derived plots. `run_tests.py` and `verify_recordings.py` are optional checks. Earlier checks included 45 passing unit/UI tests, one full in-memory CSV export per phone and unchanged hashes for all 21 source recordings. Focused plotting regressions cover all groups/panels, shading/hover in Streamlit's chart payloads, original-value precision and unchanged editor data during rendering. These are not browser screenshot or mouse-interaction tests. The full AppTest harness stalled during this fix and was stopped; the running app was not restarted. Real recordings were not re-verified for the plotting fix.

The Achromatic ledger interface direction (seed 985632799) uses neutral controls, grey original labels and blue current labels/sensor traces. The whole-file confirmation control was corrected during UI regression testing. Geist is bundled locally from Google Fonts; its license is in `assets/Geist-OFL.txt`. Streamlit/Plotly are installed from PyPI. The synthetic demo is explicitly named and does not contain your recordings.
