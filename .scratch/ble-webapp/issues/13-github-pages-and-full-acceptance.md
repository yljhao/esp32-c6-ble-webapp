# 13: GitHub repository, Pages deployment and full acceptance run

Spec: `.scratch/ble-webapp/spec.md` (Web App, Further Notes). Outward-facing: creating the repository and pushing publish the code.

**What to build:** The public repository `yljhao/esp32-c6-ble-webapp`, a GitHub Actions workflow that publishes only the Web App directory to GitHub Pages, and the Playwright run repeated against the Pages URL. Define the production state and run the whole acceptance once.

**Blocked by:** 12

**Board:** required

**Status:** ready-for-agent

- [ ] Authorized by the user 2026-09-30 (no further question needed): create the public repository, push, enable Pages. First check that nothing secret or machine-specific that should not be public is committed (tokens, keys, `prj.local.conf`-style files, the venv, build output); if anything is doubtful, park this ticket as `needs-info` instead of publishing.
- [ ] The Pages URL serves the Web App over HTTPS; the workflow run is green.
- [ ] The Playwright flows of tickets 11 and 12 pass against the Pages URL.
- [ ] The full Harness run (flash mode) passes; board-notes card lines "Verify" and "Production state" are filled in.
- [ ] README explains flashing, running the Harness, enabling the Chrome flag, and opening the Pages URL in Bluefy.
