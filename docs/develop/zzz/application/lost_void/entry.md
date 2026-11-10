# Lost Void entrance

The entrance step closes the update notice when it is visible. It then checks for the periodic or standard entrance before attempting to click the Lost Void portal. An unrecognized frame counts against the entrance step's existing retry limit.

The periodic entrance uses the Matrix Action heading and Exploration Collection button as its two screen markers. The Periodic tab remains available for navigation, so recognition also works when a performance overlay covers the tab.

If neither entrance is recognized at the limit, the step fails with an entrance recognition error. With debug mode enabled, the last captured frame is saved under `.debug/images` with the `lost_void_entry_unrecognized` prefix.
