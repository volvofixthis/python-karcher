## Why

Pause currently selects room or zone cleaning from the robot status alone. Both statuses `6` and `7` can represent either cleaning mode, so pause must inspect `sweep_type` just as resume does to avoid sending the wrong MQTT control request.

## What Changes

- For pause status `6` or `7` with `sweep_type` `1`, send a room-cleaning pause request.
- For pause status `6` or `7` with `sweep_type` `3`, send a zone-cleaning pause request.
- Reject unsupported pause status and sweep-type combinations without publishing a control request.

## Capabilities

### New Capabilities

### Modified Capabilities

- `pause-resume-commands`: Update pause routing to use sweep type for both supported pause statuses.

## Impact

- Affected pause dispatch in `karcher/cli.py`.
- Existing room and zone MQTT methods are reused.
- No new dependencies or protocol changes are required.
