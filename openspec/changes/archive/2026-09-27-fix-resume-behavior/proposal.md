## Why

The current `resume` command assumes that every supported cleaning status can be resumed directly. Robots that are docked or paused in different cleaning modes require different actions, so resume must inspect the robot's current status and sweep type before dispatching a command.

## What Changes

- Update `resume` to inspect the robot status before selecting an action.
- When status is `1`, dock the robot instead of sending a cleaning resume request.
- When status is `2`, inspect `sweep_type`.
- For status `2` with `sweep_type` `1`, resume room cleaning.
- For status `2` with `sweep_type` `3`, resume zone cleaning.
- Reject unsupported status and sweep-type combinations without publishing an unrelated control request.

## Capabilities

### New Capabilities

### Modified Capabilities

- `pause-resume-commands`: Change resume routing to account for docked and mode-specific robot state.

## Impact

- Affected resume command behavior in `karcher/cli.py`.
- Reuses existing `dock`, `set_room_clean`, and `set_zone_clean` MQTT methods.
- No new dependencies or protocol changes are required.
