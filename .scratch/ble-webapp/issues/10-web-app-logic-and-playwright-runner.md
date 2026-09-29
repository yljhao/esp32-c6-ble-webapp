# 10: Web App logic module and Playwright test runner

Spec: `.scratch/ble-webapp/spec.md` (Web App, Web App automation, Testing Decisions). ADR-0002, ADR-0004. Glossary: Web App.

**What to build:** Playwright for Python in the project venv, driving the installed Google Chrome (`channel="chrome"`, no browser download), and the Web App's pure logic module (no DOM, no Bluetooth): percent ↔ 0–255 conversion with the spec's rounding, line reassembly across chunks, line classification. Its tests run in headless Chrome through Playwright. No board is touched.

**Blocked by:** 05

**Board:** none

**Status:** ready-for-agent

- [ ] `playwright` installed in the project venv and recorded in its requirements; no `playwright install` browser download.
- [ ] Tests cover 0/50/100 % ↔ 0/128/255 both ways, reassembly across split chunks, and classification (Heartbeat, `LED`, `ERR`, noise), run headless in Chrome by one host test command.
- [ ] A broken assertion makes that command exit non-zero (red path shown, then restored).
- [ ] The Web App directory is separate from `docs/`; plain HTML/CSS/ES modules, no framework, no build step.
