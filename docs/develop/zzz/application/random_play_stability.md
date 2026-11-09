# Random Play screen checks

The video-store task uses the account's foreground keyboard method for both movement and interaction. Earlier builds offered an NPC-only scan-code option that Random Play did not call. The current keyboard controller inherits that setting when the account has no explicit keyboard method. The original game labels and screen regions are shared by both methods.

The task checks the expected NPC dialogue, ledger, or business screen before proceeding. Selecting a promoter and confirming the selection use separate frames. The task waits for the business screen before opening the video list. Named agents are matched by game name or avatar. If neither configured agent can be found, the task reports an error. The existing Random option uses the documented slots.

Manual tape selection clicks the center of the recognized theme. The shelf step checks a new frame after each click and advances only when the tape is shown as shelved. On a recognized store page after an error, the task attempts to return to the world and retains the original failure in the run record.

## Manual verification

Use a separate v2.6.1 candidate and test on a day when the store has yet to open. Keep Steam Link and Steam Input enabled and keep the game window in the foreground.

1. Open **Settings → Game settings → Key settings → Keyboard keys** and verify **Windows scan code**. Retest with the standard method if you need to compare backends.
2. Run Random Play by itself from the counter. Check that the log reports the input method and a confirmed NPC screen. Repeat from the other configured teleport points when available.
3. Test Random and a pair of eligible named promoters such as Promeia and Velina. Check that the selected promoter appears on the business page before tape selection starts.
4. Verify that tapes are selected, the game reports successful opening, and the task returns to the world. Run it again to verify the already-open path.
5. Test Scratch Card and Hou Hou Bakery on eligible days. Stop a movement task while a key is held and check that manual movement resumes.

Saved screenshots exercise recognition of particular game screens. A live Steam Link run is needed to verify delivery of input and the transitions between those screens.
