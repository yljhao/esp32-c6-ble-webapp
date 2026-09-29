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
3. **If that plan also fails**, stop: set the ticket `Status: needs-info`, summarise the attempts and both analyses, and hand it to the user. Do not weaken an acceptance criterion, skip a check, or swap an automated check for a human one to get past it.
