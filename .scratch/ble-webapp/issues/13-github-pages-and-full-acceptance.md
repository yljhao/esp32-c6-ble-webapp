# 13: GitHub repository, Pages deployment and full acceptance run

Spec: `.scratch/ble-webapp/spec.md` (Web App, Further Notes). Outward-facing: creating the repository and pushing publish the code.

**What to build:** The public repository `yljhao/esp32-c6-ble-webapp`, a GitHub Actions workflow that publishes only the Web App directory to GitHub Pages, and the Playwright run repeated against the Pages URL. Define the production state and run the whole acceptance once.

**Blocked by:** 12

**Board:** required

**Status:** ready-for-agent

- [x] Authorized by the user 2026-09-30 (no further question needed): create the public repository, push, enable Pages. First check that nothing secret or machine-specific that should not be public is committed (tokens, keys, `prj.local.conf`-style files, the venv, build output); if anything is doubtful, park this ticket as `needs-info` instead of publishing.
- [x] The Pages URL serves the Web App over HTTPS; the workflow run is green.
- [x] The Playwright flows of tickets 11 and 12 pass against the Pages URL.
- [x] The full Harness run (flash mode) passes; board-notes card lines "Verify" and "Production state" are filled in.
- [x] README explains flashing, running the Harness, enabling the Chrome flag, and opening the Pages URL in Bluefy.

## Comments

- 2026-09-30 implementation (no stuck failure, no escalation; the board notes have the full log under "Ticket 13 GitHub Pages and full acceptance").
- Secret check (tree and all 32 earlier commits, before the first push): no token, key, password, `prj.local.conf`-style file, venv or build output; author is the GitHub noreply address; only the board's and the PC adapter's MAC addresses and `~` paths remain, judged acceptable by the driver. Nothing doubtful, so the ticket was not parked.
- Repository `https://github.com/yljhao/esp32-c6-ble-webapp` (public), `main` pushed, Pages enabled with `build_type=workflow`. Workflow `.github/workflows/pages.yml` publishes `webapp/` only; run `https://github.com/yljhao/esp32-c6-ble-webapp/actions/runs/36658520504` is `success`, 19 s.
- Pages `https://yljhao.github.io/esp32-c6-ble-webapp/`: HTTP/2 200 for `/`, `app.js`, `logic.js`, `style.css`, byte-identical to `webapp/`; 404 for `CLAUDE.md`, `build.sh`, `verify.sh`, `src/main.c`, `README.md`, `tools/webtest/run.py`, `.github/workflows/pages.yml`.
- Playwright against Pages: `./verify.sh --web --web-url https://yljhao.github.io/esp32-c6-ble-webapp/` gave `RESULT: PASS (32/32 checks)`, 81 s (log `build/verify/web-20260930-101018.log`), one repeat after a PC-radio drop (`reason=0x08`, run 1), run 2 held.
- Full Harness: `./verify.sh --flash` first run `RESULT: FAIL (45/49 checks)` (PC radio `reason=0x08` in the heartbeat and shell-link scenarios, no code change), second run `RESULT: PASS (51/51 checks)`, MD5 `e7b2ab427aece2ffc27bb5f84b9bb4fc`; `./build.sh test` exit 0 (Web App logic 85/85). Board-notes card lines "Verify" and "Production state" are filled in; the board is in the production state.
- README.md at the repo root (flashing, Harness modes, Chrome flag, Bluefy); Bluefy behaviour is stated as not yet verified (ticket 14).
