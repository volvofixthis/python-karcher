## Purpose

Provide simple CLI commands that pause or resume the cleaning operation currently reported by a Kärcher Home robot.

## ADDED Requirements

### Requirement: Pause and resume commands select the active cleaning mode

The CLI SHALL provide `pause` and `resume` commands that accept a target device ID and the same authorization options as other device commands. Each command SHALL retrieve the target robot's current properties before publishing a control request.

#### Scenario: Pause room cleaning

- **WHEN** the `pause` command targets a robot whose status is `6`
- **THEN** the CLI publishes a room-cleaning control request with `ctrl_value` `2`

#### Scenario: Resume room cleaning

- **WHEN** the `resume` command targets a robot whose status is `6`
- **THEN** the CLI publishes a room-cleaning control request with `ctrl_value` `1`

#### Scenario: Pause zone cleaning

- **WHEN** the `pause` command targets a robot whose status is `7`
- **THEN** the CLI publishes a zone-cleaning control request with `ctrl_value` `2`

#### Scenario: Resume zone cleaning

- **WHEN** the `resume` command targets a robot whose status is `7`
- **THEN** the CLI publishes a zone-cleaning control request with `ctrl_value` `1`

### Requirement: Unsupported cleaning statuses are rejected

The CLI SHALL reject a pause or resume request when the target robot's current status is not `6` or `7`, and SHALL NOT publish a cleaning control request in that case.

#### Scenario: Robot is not in a supported cleaning state

- **WHEN** the `pause` or `resume` command reads a status other than `6` or `7`
- **THEN** the command reports an error and publishes no room-cleaning or zone-cleaning request

#### Scenario: Device ID is unknown

- **WHEN** the command cannot find the requested device ID
- **THEN** the command reports that the device ID was not found and publishes no request
