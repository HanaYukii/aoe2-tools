# Development and advanced use

English | [繁體中文](README.md)

Use Python 3.12+ with Tk. The app uses the standard library; packaging requires PyInstaller.

## Run from source

From the repository root:

```sh
python opponent-civ/dashboard.py --lang en
python opponent-civ/dashboard.py --demo --lang en --demo-build 33
```

The first command opens setup when needed. The second uses synthetic offline matches without requiring the game or making network requests.

| Option | Purpose |
| --- | --- |
| `--lang en` / `--lang tw` | Interface, bundled guides and game-data language |
| `--setup` | Open settings before starting |
| `--with-game` | Launch the tool, then start AoE2 through Steam |
| `--no-elo` | Disable network rating lookup |
| `--game-dir PATH` | Override the installation folder |
| `--dir PATH` | Override recording folders; repeat for multiple folders |
| `--profile-id N` | Override your player profile ID |
| `--media-dir PATH` | Optional folder of matching local videos/PDFs |
| `--demo` | Offline synthetic demo, no monitoring or network |
| `--demo-build INDEX` | Open a specific build in demo mode |

Settings and window position are saved under `%LOCALAPPDATA%\aoe2-tools\opponent-civ` on Windows, `~/Library/Application Support/aoe2-tools` on macOS, or the XDG configuration directory on Linux. Do not commit personal settings or recordings.

Language changes saved in Settings take effect after restarting. `--lang` overrides the saved choice for that run. Legacy `zh` uses Simplified Chinese game data with the Traditional Chinese interface/guides.

## Test and package

```sh
python -m unittest discover -s opponent-civ -p "test_*.py"
python -m pip install pyinstaller==6.22.3
python opponent-civ/build_exe.py
```

Build the Windows executable on Windows. Output: `opponent-civ/build/release/aoe2-opponent-dashboard.exe` and `SHA256SUMS.txt`. The packaging check runs the actual EXE from an empty directory and validates both language catalogs. Add `--desktop` to copy it to the Windows desktop.

Pushing a `v*` tag triggers tests, packaging and a GitHub Release. A manual workflow run produces a build artifact without publishing a release.

## Guide data and localization

- `data/builds.zh-TW.json` / `data/builds.en.json`: 40 builds and tactical cards. English follow-up notes are concise adaptations; step allocations retain the same values.
- `data/map-notes.zh-TW.json` / `data/map-notes.en.json`: map guidance. IDs and matching aliases remain the same across languages.
- `data/ui.en.json` / `i18n.py`: interface translations and catalog selection.
- Keep build/sheet IDs stable so personal recommendations survive updates and language changes.
- `build_ids` links sheets to openings. `civ` restricts a sheet to a civilization; `maps` restricts it by map. Era/navigation labels organize Roman branches.
- Reference cards use one to three columns, fitting text to available space and scrolling when necessary. Both English technology names and worker allocations are highlighted.

Game civilization and unit text is read directly from the installed language resources. Unit counters use the game's English description patterns; missing counters are not invented. Map matching prefers built-in IDs and exact aliases for custom maps.

## Main modules

| Module | Responsibility |
| --- | --- |
| `dashboard.py`, `settings.py` | Desktop UI, setup and background rating lookup |
| `rec_header.py` | Match participants, civilizations and map from replay headers |
| `history.py`, `savegames.py` | Recent recordings and player identification |
| `civdata.py`, `units.py`, `mapdata.py` | Installed-game text and metadata |
| `build_library.py`, `build_views.py`, `map_notes.py` | Bundled guides and their views |
| `launcher.py` | Steam launch and window placement |
| `demo.py` | Synthetic demonstration matches |
| `verify_offline.py` | Diagnose local replay-header compatibility |

macOS demo mode does not verify Windows recording monitoring or multi-monitor APIs. The separate local AoE Buddy review prototype is not part of this app or its release.
