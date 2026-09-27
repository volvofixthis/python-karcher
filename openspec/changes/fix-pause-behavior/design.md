## Context

The pause dispatcher currently receives device properties and already shares control payload handling with resume. Pause statuses `6` and `7` do not uniquely identify room versus zone cleaning; `sweep_type` is the mode discriminator used by resume.

## Goals / Non-Goals

**Goals:**

- Route pause status `6` and `7` through the same sweep-type mapping as resume.
- Preserve pause control value `2` and existing room/zone MQTT payloads.
- Reject unsupported pause combinations before publishing.

**Non-Goals:**

- Changing resume routing.
- Changing CLI options or MQTT method signatures.
- Adding new protocol methods or dependencies.

## Decisions

- Treat `(status in {6, 7}, sweep_type == 1)` as room pause and `(status in {6, 7}, sweep_type == 3)` as zone pause. This directly mirrors the established resume mode mapping while retaining both pause statuses.
- Keep the status and sweep-type validation in the CLI dispatcher so invalid combinations fail before any MQTT method is called.
- Continue passing an empty room list for room pause because no room selection is provided by the top-level pause command.

## Risks / Trade-offs

- [Robot status and sweep type are protocol-specific] -> Cover all four supported status/mode combinations and invalid combinations with deterministic tests.
- [Robot state can change between property retrieval and publication] -> Make one routing decision immediately before using the existing MQTT methods.
