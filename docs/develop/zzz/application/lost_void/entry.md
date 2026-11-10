# Lost Void entrance

The entrance step closes the update notice when it is visible. It then checks for the periodic or standard entrance before attempting to click the Lost Void portal. An unrecognized frame counts against the entrance step's existing retry limit.

If neither entrance is recognized at the limit, the step fails with an entrance recognition error. With debug mode enabled, the last captured frame is saved under `.debug/images` with the `lost_void_entry_unrecognized` prefix.
