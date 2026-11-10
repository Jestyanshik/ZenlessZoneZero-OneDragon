# Daily NPC interaction

The scratch card and bakery tasks first verify an expected screen marker. They allow up to three presses with a fresh screenshot between attempts. The scratch-card task moves forward once, before the first press. The bakery's centered-box screen tries the existing mouse click first, then tries the configured interaction key once if the screen persists.

The scratch-card task also recognizes the sleeping NPC dialogue and its **Wake him up!** option as evidence that interaction has opened. It then uses the existing dialogue and ticket flow.

Under **Settings → Game settings → Key settings → Keyboard keys**, **Keyboard input method** selects the input method for foreground game keys. **Standard (pynput)** is the default for new accounts. **Windows scan code** also applies to these tasks' movement and interaction keys. The setting is per account. Background mode retains its existing gamepad input.

The standard backend sends a virtual key when the character maps cleanly to the active layout. Otherwise pynput may use Unicode text input. Scan-code mode sends a key position and logs whether Windows accepted both events. The game must still be observed to confirm receipt. Steam Input legacy keyboard bindings also use scan codes, but the behavior of the user's Steam Link session requires a live test.

## Test with Steam Link

1. Leave Steam Link and Steam Input enabled, and keep the game in the foreground. In OneDragon, leave background mode off and set the interaction binding to match the game's binding.
2. Run the scratch-card task by itself with **Standard (pynput)**. If the NPC screen fails to open, select **Windows scan code** and rerun it without manually pressing the interaction key.
3. Test the bakery separately. Since these tasks share one daily reward, use a different account or day to verify both rewards can be claimed.
4. Check `.log/log.txt` for the input method, the configured key, and the recognized screen. For the bakery, the log separates the NPC opening from the centered-box click and key retry. If Windows accepted the events and the screen still did not change, record the active keyboard layout and what happened when pressing the same key through Steam Link.
