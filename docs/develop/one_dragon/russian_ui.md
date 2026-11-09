# Russian interface

## Launch and language selection

In the main window, open **Settings → Appearance → Interface language**. Choose **Русский** and restart. **简体中文** restores the Chinese interface. **English** remains available, and **Follow system** selects Russian on Russian Windows installations. The application stores the selection in the existing `ui_language` field of `config/custom.yml`.

With a source checkout and the project dependencies installed, run:

```powershell
$env:PYTHONPATH = 'src'
uv run --locked -m zzz_od.gui.app
```

With a patched v2.6.1 WithRuntime installation, start `OneDragon-RuntimeLauncher.exe`. Turn off **Auto-update** under the OneDragon environment settings for this copy before using the integrated launcher. The startup synchronizer can check out the configured upstream branch or replace local source changes when forced updates are enabled.

## Translation boundary

The Russian catalog is `assets/text/ui/ru.po`. The shipped `ui.mo` lets the existing runtime load it without development dependencies. Python passes labels, tooltips and messages through `gt()` at their presentation points. Qt and Fluent Widgets supply translations for their standard controls.

The UI language is selected before the first widgets are built. The Russian selection uses the existing Chinese or English default for non-UI domains, based on the system locale. The bundled Chinese and English game catalogs in v2.6.1 contain no translated game messages, so both return the original text. A missing Russian UI message returns its source string.

Keep agent identifiers, widget route keys, account and profile names, combobox item data, command strings, screen regions, and OCR strings in their existing form. Translate labels at their point of display. In particular, do not pass translated labels into configuration fields or matching code. Some third-party plugin metadata, game images, diagnostic output, and content loaded from remote services are supplied by their original authors.

## Build and carry forward

After changing the catalog, compile the Russian UI resource from the project root:

```powershell
$env:PYTHONPATH = 'src'
uv run --locked --group dev python -c "from one_dragon.devtools.compile_po import compile_lang; compile_lang('ui', 'ru')"
```

For a later OneDragon release, start with a clean checkout of its release tag on a separate branch. Run `git apply --check <patch>` before applying the localization patch. If the check fails, reconcile the affected code against the new version. Reuse the PO catalog and rebuild the MO resource. Review new UI keys and run the tests again before deploying the patch. Use a separate checkout for updates and back up the installation's configuration before moving it to a new release.

The localization patch contains application code, catalogs, and this guide. Applying it does not write user configuration files. The accompanying tests belong in the separate `zzz-od-test` checkout.

Official terminology references:

- [Russian Zenless Zone Zero character roster](https://zenless.hoyoverse.com/ru-ru/main)
- [Version 3.3 notes and game terminology](https://zenless.hoyoverse.com/ru-ru/news/166963)
- [Hollow Zero event announcement](https://zenless.hoyoverse.com/ru-ru/news/154348)
- [Version 2.1 notes and Suibian Temple terminology](https://zenless.hoyoverse.com/ru-ru/news/157696)
