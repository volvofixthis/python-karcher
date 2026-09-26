## Why

Users currently need to know whether the robot is performing room or zone cleaning before issuing an existing control command. Dedicated `pause` and `resume` commands provide a simple status-aware interface for the two supported cleaning modes.

## What Changes

- Add top-level CLI commands named `pause` and `resume`.
- Resolve the requested device and read its current robot status before sending a cleaning control command.
- Route status `6` to room cleaning and status `7` to zone cleaning.
- Send the corresponding pause or resume control value: pause `2`, resume `1`.
- Reject unsupported robot statuses without publishing an MQTT command.

## Capabilities

### New Capabilities

- `pause-resume-commands`: Status-aware CLI commands for pausing and resuming active room or zone cleaning.

### Modified Capabilities

## Impact

- Affected CLI entrypoints in `karcher/cli.py`.
- Existing device property retrieval and `set_room_clean`/`set_zone_clean` MQTT methods will be reused.
- No new dependencies or protocol changes are required.
