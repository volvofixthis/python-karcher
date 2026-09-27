## 1. Resume Dispatch

- [x] 1.1 Separate resume routing from pause routing while preserving pause status `6`/`7` behavior; verify existing pause tests continue to pass.
- [x] 1.2 Route resume status `1` to the existing dock/recharge-start method without publishing a cleaning request; verify the dock method receives the requested device and QoS.
- [x] 1.3 Route resume status `2` with `sweep_type` `1` to room cleaning and `sweep_type` `3` to zone cleaning, using resume control value `1`; verify both dispatch paths and parameters.
- [x] 1.4 Reject unsupported resume statuses and sweep types before dispatch, while preserving unknown-device handling; verify no MQTT control method is called.

## 2. Tests And Verification

- [x] 2.1 Add deterministic unit coverage for dock, room resume, zone resume, unsupported state, unsupported sweep type, and pause regression behavior; verify the focused CLI tests pass.
- [x] 2.2 Run `python -m unittest discover -s tests -p 'test_*.py'` and `python -m compileall karcher` to verify the full test suite and bytecode compilation.
