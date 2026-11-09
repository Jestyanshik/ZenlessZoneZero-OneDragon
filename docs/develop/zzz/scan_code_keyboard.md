# Scan-code keyboard input

The per-account keyboard setting is under **Settings → Game settings → Key settings → Keyboard keys**. Select **Windows scan code** to use physical game keys in foreground mode. Existing accounts default to the standard backend unless they had explicitly selected scan-code input in the earlier NPC-only setting.

The controller interprets printable bindings as US keyboard positions. Use named modifiers, for example `shift+w`, for a chord. Windows extended scan codes are handled for supported named keys. An unsupported binding reports an error. Text entry uses the existing character input path. Mouse actions and the virtual gamepad keep their existing backends.

The controller tracks keys that it pressed and releases them on pause, stop, shutdown, and failure during a chord. A Windows rejection is reported separately from the game's observed screen state.

For a live check, run with Steam Link and Steam Input enabled. Test the video store, Scratch Card, and Hou Hou Bakery with Russian and English Windows layouts. Check movement, menu navigation, a short combat run, and stopping while movement is held. Use separate days or accounts for the two daily reward tasks.
