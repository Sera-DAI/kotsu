---
name: verify
description: Run Kotsu's full check and an end-to-end smoke test with temporary data, then report what was verified and what was skipped. Use before opening a PR.
---

# verify

1. Run `python tools/check.py` (full). It stamps HEAD for the push gate only when the tree is
   clean and committed. Fix failures, at most 3 rounds, then stop and call the maintainer with
   the log of each round.
2. Smoke test with a temporary folder, never the real data folder:
   - `kotsu --data <tmp> --export <tmp>/a.json` on an empty database, then
     `kotsu --data <tmp> --verify`, `kotsu --data <tmp> --verify <tmp>/a.json` and
     `kotsu --data <tmp> --import <tmp>/a.json`.
   - The Textual pilot tests in `tests/test_ui.py` open the app, switch months and start the
     real process. The other TUI flows (quick line, installments, filter, backup `b`, theme
     `t`) have no pilot test yet: open `kotsu --data <tmp>` and try them by hand, or report
     them as a **limitation**.
3. Run the smoke test 3 times in a row to prove it is stable.
4. Detect the system (`sys.platform`). Android (`gradle -p android :core:test`) needs a JDK 17
   and Gradle; where they are missing, report the step as **skipped**.
5. Report: verified, skipped (with the reason) and limitations (what only runs on the real
   platform, such as Windows Terminal rendering or a real phone). Never write "verified" for
   what was only seen at a glance.
