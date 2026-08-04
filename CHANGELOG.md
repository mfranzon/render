# Changelog

## Unreleased (2026-08-04)

### Added

- **Dimension overlay** (`□ dims`): bounding box plus W/D/H labels that track
  the camera.
- **One model per slug.** Renders are named from the description
  (`gear_12_teeth.py`) instead of everything overwriting `script.py`, so the
  gallery keeps a browsable history.
- The code panel loads the script belonging to the displayed model rather than
  always showing `script.py`.

### Fixed

- **Viewer no longer fails silently on a bad model.** `loadModel` had no error
  handler, so a `.glb` read while it was still being written left the previous
  model on screen with a stale HUD and no retry. It now retries on the next poll
  up to 3 times, then reports the failure in the HUD.
- **`setup.sh` writes its ready marker on a fresh install.** Only the fallback
  branch created `.b3d-ready`, so the first render after installing paid a full
  `import build123d` before the marker appeared.
- **STEP download accepts names with spaces** (`unquote` on the path segment)
  and stays confined to `viewer/models/`.
- **Gallery panel state.** Deleting every model left stale entries in the list,
  and rebuilding the list detached the "no models yet" node so it could never
  reappear.
- **`stepBtn` is declared before `poll()` uses it**, instead of relying on an
  `await` to dodge the temporal dead zone.
- **`argument-hint` is quoted** in the skill frontmatter (PR #6). Unquoted, YAML
  parsed it as a one-element list rather than a string.

### Changed

- Server binds `127.0.0.1` instead of all interfaces. The viewer is a local tool
  and was reachable from the LAN.
- Browser `Run` timeout raised from 30s to 300s (`RUN_TIMEOUT`), so heavy
  infill and boolean models behave the same in the code panel as from the CLI.
- The skill no longer arms a `ScheduleWakeup` loop on every render. It mentions
  the `/loop /render apply pending edits` command once and arms the loop only
  when asked, instead of polling an empty queue every 60s for the whole session.
- `serve.py` shares one `sorted_glbs()` / `step_sibling()` pair across
  `get_model_version`, `send_latest` and `list_models`.

### Documentation

- Skill frontmatter pointed at `viewer/edits/latest.{png,json}`; the real queue
  is `viewer/edits/pending/<id>.{png,json}`.
- `ScheduleWakeup` added to `allowed-tools`, which previously blocked the
  hands-free edit loop the skill told Claude to arm.
- README: the hands-free loop is a ~60s poll you start yourself, not a 1s file
  watcher; `render()` also emits `.stl` plus a copy of the model script; added
  the `dims` overlay to the feature list; noted that the viewer page fetches
  three.js from a CDN on first load.

### Repository

- `.gitignore` covers all generated output under `viewer/models/` (previously
  `.stl` files, added later than the other exporters, showed up as untracked)
  and `.DS_Store`.
