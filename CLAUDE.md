## Agent skills

### Issue tracker

Issues and specs live as local markdown under `.scratch/<feature>/` (GitHub remote planned for Pages only). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, recorded as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Board notes

XIAO ESP32-C6 (`xiao_esp32c6/esp32c6/hpcore`) on `/dev/ttyACM0`, flashed through esptool-build (`west flash` day to day, `build.sh flash` pinned to `--chip esp32c6` for acceptance; ADR-0003). Platform facts live in `docs/agents/board-notes.md`: read it before building, append what you learn before finishing.

## Escalation when stuck

"Stuck" means three attempts at the same failure without progress: the same acceptance criterion still red, the same build or test error, or the same board symptom after three distinct fixes. Count per failure, and log each attempt (what was tried, the evidence, the result) under `## Comments` in the ticket file.

1. **After the third failed attempt**, spawn an Opus agent (Agent tool, `model: "opus"`) with the ticket path, the attempt log, the exact error or capture excerpt, and the relevant files. It analyses and proposes a fix; the implementing session applies it and does all board work itself (subagents never touch the board). Log the Opus analysis in the ticket.
2. **If three more attempts with the Opus proposals still fail**, spawn a Fable agent (`model: "fable"`) and give it the full attempt log plus the Opus analysis, asking it to challenge the diagnosis and propose a different approach; relay between Opus and Fable (SendMessage to the running agents) until they agree on a plan or name what is unknown. Log the outcome in the ticket.
3. **If that plan also fails**, park the ticket: set `Status: needs-info`, summarise the attempts and both analyses in it, and move on (see Unattended runs). Do not weaken an acceptance criterion, skip a check, or swap an automated check for a human one to get past it.

## Unattended runs

Implementation runs without a human watching. Never wait for an answer mid-run.

- Work tickets in number order. A ticket that is parked (`Status: needs-info`) blocks only the tickets that list it under `Blocked by`; continue with the next ticket whose blockers are all done.
- Anything only a human can do (ticket 14's Bluefy run, a physical check, a decision a ticket says belongs to the user) is not attempted mid-run: record it and leave it for the end.
- The user authorized on 2026-09-30 creating the public repository `yljhao/esp32-c6-ble-webapp`, pushing to it and enabling GitHub Pages without asking again (ticket 13). The secret and machine-specific-content check still runs first; if anything looks doubtful, park ticket 13 instead of publishing.
- When no ticket is left that can run, write `.scratch/ble-webapp/run-report.md`: per ticket done / parked / not started, commits, Harness `RESULT:` of the last full run, each parked ticket's blocker in one paragraph, and the human checks waiting for the user in order (ticket 14 last).
- Leave the board in the production state at the end (or, if ticket 13 never ran, on the newest image that passes the Harness), and say which in the report.
