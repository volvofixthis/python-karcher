## MODIFIED Requirements

### Requirement: Pause and resume commands select the active cleaning mode

The CLI SHALL provide `pause` and `resume` commands that accept a target device ID and the same authorization options as other device commands. Each command SHALL retrieve the target robot's current properties before publishing a control request. The `pause` command SHALL route status `6` or `7` with `sweep_type` `1` to room cleaning and with `sweep_type` `3` to zone cleaning. The `resume` command SHALL route status `1` to docking, and SHALL route status `2` according to `sweep_type`: `1` to room cleaning and `3` to zone cleaning.

#### Scenario: Pause room cleaning

- **WHEN** the `pause` command targets a robot whose status is `6` or `7` and whose `sweep_type` is `1`
- **THEN** the CLI publishes a room-cleaning control request with `ctrl_value` `2`

#### Scenario: Pause zone cleaning

- **WHEN** the `pause` command targets a robot whose status is `6` or `7` and whose `sweep_type` is `3`
- **THEN** the CLI publishes a zone-cleaning control request with `ctrl_value` `2`

#### Scenario: Resume a docked robot

- **WHEN** the `resume` command targets a robot whose status is `1`
- **THEN** the CLI publishes a dock request and no cleaning control request

#### Scenario: Resume room cleaning

- **WHEN** the `resume` command targets a robot whose status is `2` and `sweep_type` is `1`
- **THEN** the CLI publishes a room-cleaning control request with `ctrl_value` `1`

#### Scenario: Resume zone cleaning

- **WHEN** the `resume` command targets a robot whose status is `2` and `sweep_type` is `3`
- **THEN** the CLI publishes a zone-cleaning control request with `ctrl_value` `1`

### Requirement: Unsupported cleaning statuses are rejected

The CLI SHALL reject a pause request when the target robot's status is not `6` or `7`, or when its `sweep_type` is not `1` or `3`. The CLI SHALL reject a resume request when the current status is not `1` or `2`, or when status `2` has a `sweep_type` other than `1` or `3`. Rejected requests SHALL publish no cleaning or docking control request.

#### Scenario: Robot is not in a supported cleaning state

- **WHEN** the `pause` command reads a status other than `6` or `7`
- **THEN** the command reports an error and publishes no request

#### Scenario: Resume uses an unsupported status

- **WHEN** the `resume` command reads a status other than `1` or `2`
- **THEN** the command reports an error and publishes no request

#### Scenario: Resume uses an unsupported sweep type

- **WHEN** the `resume` command reads status `2` with a `sweep_type` other than `1` or `3`
- **THEN** the command reports an error and publishes no request

#### Scenario: Device ID is unknown

- **WHEN** the command cannot find the requested device ID
- **THEN** the command reports that the device ID was not found and publishes no request
