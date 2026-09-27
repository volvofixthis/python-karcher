## 1. Pause Dispatch

- [ ] 1.1 Route pause status `6` and `7` with `sweep_type` `1` to room cleaning and `sweep_type` `3` to zone cleaning; verify all four status/mode combinations.
- [ ] 1.2 Preserve pause control value `2`, empty room IDs for room pause, and existing QoS/timeout handling; verify generated method arguments.
- [ ] 1.3 Reject unsupported pause statuses and sweep types without publishing a control request; verify clear errors and no MQTT method calls.

## 2. Tests And Verification

- [ ] 2.1 Add or update deterministic CLI tests for pause routing, invalid combinations, and resume regression behavior; verify the focused tests pass.
- [ ] 2.2 Run `python -m unittest discover -s tests -p 'test_*.py'` and `python -m compileall karcher` to verify the full test suite and compilation.
