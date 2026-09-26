## Context

The CLI already resolves devices, retrieves device properties, and exposes separate room and zone cleaning controls. The robot property `status` identifies the active cleaning mode for this feature: `6` means room cleaning and `7` means zone cleaning. Existing control methods use `RoomCleanControl.RESUME` (`1`) and `RoomCleanControl.PAUSE` (`2`).

## Goals / Non-Goals

**Goals:**

- Add concise `pause` and `resume` commands using the existing CLI authorization flow.
- Select the correct MQTT control method from the live robot status.
- Keep control values centralized through the existing room-clean control enum/parser.

**Non-Goals:**

- Changing the existing `set_room_clean` or `set_zone_clean` commands.
- Supporting pause/resume for statuses other than `6` and `7`.
- Introducing a new MQTT method or dependency.

## Decisions

- Implement the commands in `karcher/cli.py`, matching the existing device-command decorators and `run_authorized_command` flow. This avoids duplicating authentication and session handling.
- Retrieve properties after resolving the device, then branch on `props.status`. Status `6` calls the existing room-clean method (the API method currently named `set_room_clean`); status `7` calls the existing zone-clean method.
- Pass `RoomCleanControl.PAUSE` for `pause` and `RoomCleanControl.RESUME` for `resume`. This preserves the protocol values `2` and `1` without embedding unexplained numeric literals in command logic.
- Raise a Click parameter error for unsupported statuses so callers receive a clear failure and no MQTT command is sent.
- Expose the existing MQTT `qos` and `timeout` controls where needed by the reused methods, with the same defaults as the current cleaning commands.

## Risks / Trade-offs

- [Robot status can change between property retrieval and command publication] -> The command makes one immediate status decision and relies on the existing MQTT reply behavior; it does not add a second status race window or invent new protocol handling.
- [Status values are protocol-specific] -> Keep the mapping documented in the requirement and isolated to these commands so future protocol changes are localized.
