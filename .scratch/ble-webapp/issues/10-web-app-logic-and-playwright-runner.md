# 10: Web App logic module and Playwright test runner

Spec: `.scratch/ble-webapp/spec.md` (Web App, Web App automation, Testing Decisions). ADR-0002, ADR-0004. Glossary: Web App.

**What to build:** Playwright for Python in the project venv, driving the installed Google Chrome (`channel="chrome"`, no browser download), and the Web App's pure logic module (no DOM, no Bluetooth): percent ↔ 0–255 conversion with the spec's rounding, line reassembly across chunks, line classification. Its tests run in headless Chrome through Playwright. No board is touched.

**Blocked by:** 05

**Board:** none

**Status:** done

- [x] `playwright` installed in the project venv and recorded in its requirements; no `playwright install` browser download.
- [x] Tests cover 0/50/100 % ↔ 0/128/255 both ways, reassembly across split chunks, and classification (Heartbeat, `LED`, `ERR`, noise), run headless in Chrome by one host test command.
- [x] A broken assertion makes that command exit non-zero (red path shown, then restored).
- [x] The Web App directory is separate from `docs/`; plain HTML/CSS/ES modules, no framework, no build step.

## Comments

- 2026-09-30 (implementer, `Board: none`, no board, serial or Bluetooth touched). No failure was stuck: nothing needed a second attempt.
- Evidence: `playwright` 1.63.0 in `.venv`, `playwright>=1.49` in `tools/requirements.txt`, no `~/.cache/ms-playwright`, Chrome 154.0.8037.92 launched with `channel="chrome"`. `./build.sh test-web` (run by `./build.sh test`): `RESULT: PASS (77/77 tests, 0 page error(s))`, tests for 0/50/100 % <-> 0/128/255, 18 reassembly cases, 48 classification cases. `./build.sh test` exit 0 (twister 65/65, guard test, tools/verify 238 tests, tools/webtest 4 tests, web 77/77).
- Red path: `Math.floor` in `percentToBrightness` gave `FAIL  0 % -> 0, 50 % -> 128, 100 % -> 255: expected 128, got 127` (+3 more) and `RESULT: FAIL (73/77 tests, 0 page error(s))`, `./build.sh test-web` exit 1; restored, exit 0.
- Decisions where the spec was silent (details in board-notes, Ticket 10): exact halves round up; out-of-range input throws instead of clamping; `LED <n>` must be 0-255 without sign or leading zeros; `uptimeMs` is a Number; `webapp/index.html` and `style.css` are placeholders for tickets 11 and 12. Shared fixtures `tools/webtest/fixtures/wire_lines.json` tie `webapp/logic.js` to `central_logic.py`; the review found and fixed two differences (`-0`, RecursionError on deep nesting in `central_logic.py`).
