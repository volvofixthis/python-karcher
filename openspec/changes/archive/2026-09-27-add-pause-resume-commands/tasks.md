## 1. CLI Commands

- [x] 1.1 Add the `pause` and `resume` Click commands with device identification, authorization, QoS, and timeout options matching existing device commands; verify both commands appear in `karcher-home --help`.
- [x] 1.2 Resolve the target device and retrieve its current properties before dispatch; verify unknown device IDs produce the existing Click error and no control method is called.
- [x] 1.3 Map status `6` to room cleaning and status `7` to zone cleaning, passing pause value `2` or resume value `1`; verify each status/action combination calls only the expected control method.
- [x] 1.4 Reject statuses other than `6` and `7` without publishing an MQTT request; verify the command reports a clear Click error.

## 2. Tests And Verification

- [x] 2.1 Add deterministic CLI unit coverage for pause/resume routing, control values, missing devices, and unsupported statuses; verify the focused test module passes with `python -m unittest`.
- [x] 2.2 Run `python -m unittest discover -s tests -p 'test_*.py'` to verify the full existing test suite; Ruff was not run because it is not installed and was explicitly deemed unnecessary.
