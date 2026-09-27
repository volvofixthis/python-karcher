## Context

The existing `resume` command shares the status-aware cleaning dispatcher with `pause`, but resume now needs a different state mapping. Robot status `1` means the robot should be docked. Status `2` identifies a resumable cleaning operation whose `sweep_type` selects room cleaning (`1`) or zone cleaning (`3`).

## Goals / Non-Goals

**Goals:**

- Preserve the current pause routing for statuses `6` and `7`.
- Route resume requests using status and, when required, sweep type.
- Reuse the existing dock, room-clean, and zone-clean MQTT methods.

**Non-Goals:**

- Changing the public options or behavior of the existing `pause`, `set_room_clean`, `set_zone_clean`, or `dock` commands.
- Supporting resume for other status or sweep-type values.
- Adding new MQTT protocol methods.

## Decisions

- Keep `pause` and `resume` as separate dispatch paths in the shared CLI helper. A single status map is no longer sufficient because pause uses statuses `6`/`7`, while resume uses status `1`/`2` plus `sweep_type`.
- For resume status `1`, call the existing recharge-start method used by the dock command. This preserves the established dock protocol instead of publishing a cleaning request.
- For resume status `2`, branch on `sweep_type` and pass `RoomCleanControl.RESUME` to the corresponding room or zone method.
- Raise a Click parameter error before dispatch for unsupported status or sweep-type combinations.

## Risks / Trade-offs

- [Status and sweep-type values are protocol-specific] -> Keep the mapping isolated in the resume dispatcher and cover every supported combination with deterministic tests.
- [Robot state can change between property retrieval and publication] -> Make one status decision immediately before using the existing MQTT methods; do not add a second protocol request.
