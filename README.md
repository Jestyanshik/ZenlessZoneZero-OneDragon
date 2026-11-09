# OneDragon Russian fork

This is an unofficial fork of [ZenlessZoneZero-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon). The initial fork is based on official `v2.6.1` (`3cbeda9e20a0bf1ab84ab56861bb01b7ee668aa8`). The original project history, copyright notices, and [GNU GPL v3 license](LICENSE) are retained.

## Changes

- Russian application interface through gettext. Russian, Simplified Chinese, English, and the system-language option are available. Game text used for recognition is kept in its existing domains.
- Optional physical Windows scan-code input for foreground game keys, including movement, menus, and combat through the shared controller. The standard backend remains available.
- Verified screen transitions and bounded interaction attempts for Scratch Card, Hou Hou Bakery, and Random Play. The video store checks its three documented entry paths.

## Install

For the Windows archive, open **Actions → Fork verification and Windows artifact**, run the workflow on the maintained branch with **Build an unsigned Windows snapshot artifact** selected, then download the **OneDragon-Fork-windows** artifact from the successful run. Extract GitHub's artifact and the enclosed archive into a new directory. Run `OneDragon-RuntimeLauncher.exe`. The archive contains the embedded Python runtime and corresponding source. Download optional OCR and other game models through the application's resource tools as needed.

The archive is an unsigned snapshot. Its launcher skips automatic source replacement. The fork also guards its in-app Git commands so they cannot replace the fork with upstream code or change its remotes. Version checks and resource downloads are separate operations. Keep the previous installation and its configuration until you have tested the new copy.

For a source checkout on Windows with Python 3.11 and uv:

```powershell
$env:VGAMEPAD_SKIP_VIGEMBUS_INSTALL = 'true'
uv sync --locked --group dev
$env:PYTHONPATH = 'src'
uv run --no-sync python -m zzz_od.gui.app
```

To build from the current committed source using this environment:

```powershell
uv run --no-sync python tools/fork/build_windows.py --output dist/OneDragon-Fork-windows.zip
```

The build tool uses the upstream PyInstaller runtime specification. It packages tracked source and the generated runtime, then runs the extracted launcher with `--version`. No GitHub Release is created. Keep the archive separate from the existing installation.

## Enable Russian and scan-code input

1. Open **Settings → Appearance → Interface language**, choose **Русский**, and restart. **简体中文** switches back to Simplified Chinese.
2. Open **Settings → Game settings → Key settings → Keyboard keys → Keyboard input method**. Select **Windows scan code**.
3. Keep the game in the foreground. Match the game's bindings, such as WASD and F. Scan-code mode interprets printable keys as physical US key positions. Use explicit modifiers for combinations, for example `shift+w`.

Text entry, mouse actions, OCR targets, and the virtual gamepad follow their existing paths. The shared backend does not guarantee that every other NPC interaction is recognized. Those flows keep their existing screen checks.

## Update the fork

The maintained branch carries the fork commits. The `upstream` remote tracks the official project and `origin` points to this fork. A dedicated long-lived upstream-sync branch is unnecessary.

From the maintained branch, prepare an update in a separate worktree:

```powershell
.\tools\fork\prepare-update.ps1
.\tools\fork\prepare-update.ps1 -Tag v2.6.1
```

With no tag, the script queries the latest stable official release. It prints upstream commits, creates a `codex/upstream-<tag>` branch for a newer release, merges the official tag, and runs the fork checks. Conflicts or failed checks leave the review worktree available. If reusing a compatible Python environment, pass `-Python 'C:\path\to\python.exe'`. Otherwise the review worktree uses locked dependencies via uv.

By default the script prepares the update locally. Use `-OpenDraft` only when you want to push the update branch and open a draft PR in the verified fork. This requires an authenticated GitHub CLI, Git credentials for the fork, and a local base matching the published branch. The script never merges the PR. Review and test the update before switching installations.

## Verification and limitations

The fork-specific workflow checks modified Python files, PO/MO consistency, scan-code behavior with mocked Windows events, and observed NPC state transitions. It builds downloadable Windows artifacts on manual dispatch. Upstream publishing and maintenance workflows are restricted to the official repository.

For local regression checks:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONPATH = 'src'
uv run --no-sync python -m pytest -q tools/fork/checks.py
```

The upstream screenshot and flow suite lives in [zzz-od-test](https://github.com/OneDragon-Anything/zzz-od-test). Select a revision compatible with the official source and provide the required OCR models before running its image tests. The fork checks and the saved-frame OCR tests do not establish compatibility with a live Steam Link session.

For in-game acceptance, keep Steam Link and Steam Input enabled. Test both Windows layouts, map navigation, movement and menu keys, stopping during a held key, and each of the three NPC activities. Use separate days or accounts for Scratch Card and Hou Hou Bakery because they share a daily reward. The package does not include drivers, personal settings, or game models.
