# 09: Heartbeat

Spec: `.scratch/ble-webapp/spec.md` (Heartbeat rules, Wire contract). Glossary: Heartbeat. Reference heartbeat module and suite in `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2` (counts from a broker session there; here it counts from boot).

**What to build:** `seq` starts at 0 at boot and advances once a second whether or not a Central listens; a missed period is consumed, not queued. While a Central is subscribed the board sends one `{"seq":N,"uptime_ms":N}` line per second over the Shell link, and prints `[HB] seq=N` on the serial console every tenth Heartbeat. The main loop that emits Heartbeats is the one that feeds the watchdog.

**Blocked by:** 07

**Board:** required

**Status:** ready-for-agent

- [x] The Harness receives 10 s of Heartbeat lines with consecutive `seq` and 1 s ± 200 ms spacing, interleaved correctly with `led` replies sent during that time.
- [x] After a 5 s disconnect the first `seq` received is about 5 higher than the last one before it.
- [x] After a reboot `seq` starts again near 0.
- [x] `[HB] seq=N` appears on the serial console every tenth Heartbeat.
- [x] Heartbeat host suite (ported and adapted) passes under `./build.sh test`, including encoding at maximum values.
- [x] Harness Checks for the above.

## Comments

2026-09-30（implementer；`./verify.sh --flash` 於映像 MD5 `e7b2ab427aece2ffc27bb5f84b9bb4fc`、542672 bytes，`RESULT: PASS (51/51 checks)`，08:00 前後；輸出留在 `build/verify/final-flash-ticket09.txt`，主控台紀錄 `build/verify/heartbeat-20260930-075941.log`）：

- 設計與量測全文在 `docs/agents/board-notes.md` 的 `### Ticket 09 Heartbeat`。主迴圈只把 `seq` 丟進 3 格的 `k_msgq`（`K_NO_WAIT`，滿了就丟最舊的），由獨立的 `heartbeat_sender` 執行緒編碼並經 `shell_nus_notify()`（同一把 TX lock）送出；Heartbeat 不經過 `link_filter` 與 `transport_read`。
- 框 1：`Heartbeat: 10 s of lines with consecutive seq, 1 s +- 200 ms apart` PASS（`11 heartbeats, seq 15..25 consecutive, period 0.945..1.035 s`）；`led replies ... whole lines between the Heartbeats, none spliced` PASS（`11 Heartbeat line(s) and 9 reply line(s), all whole, 8 reply(ies) between Heartbeats`）；整條串流只有 Heartbeat 與回覆行 PASS（21 行、420 bytes）。
- 框 2：`after a 5 s disconnect the first seq is 5 or more higher` PASS（`seq 25 -> 34: 9 higher after 9.05 s`，含 5 s 斷線加約 4 s 掃描、連線、訂閱）；重連後 `board period 1000..1000 ms`。
- 框 3：`after kernel reboot on the serial shell the first seq is near 0` PASS（`seq 46 -> 2 (uptime_ms 49665 -> 5703)`）。
- 框 4：`console: [HB] seq=N on every tenth Heartbeat, the same numbers as on the Shell link` PASS（`3 markers, seq 20..40 every 10, matched Shell link seq [20, 40]`；主控台 `07:59:49.304 [HB] seq=20`、`07:59:59.307 [HB] seq=30`、`08:00:09.305 [HB] seq=40`）。
- 框 5：`./build.sh test`：`65 of 65 executed test cases passed`（新 suite `c6.heartbeat` 13 案，含最大值編碼 53 bytes 與少一 byte 回 -1），esptool guard 全過，`Ran 234 tests ... OK`。
- 框 6：Harness Checks 在 `tools/verify/verify.py`（`run_heartbeat`、`heartbeat_scenario`、`steady_window`），邏輯在 `central_logic.py`（`check_interleaved`、`check_gap_after_disconnect`、`check_restart_after_reboot`、`check_board_spacing`）與 `checks.py`（`check_hb_markers`、`check_stall_survived`），皆有 unittest。另有 `./verify.sh --stall`（debug 映像 `debug stall`，證明卡住的連結餓不死看門狗）：`no reset in 29.0s after the stall, 3 [HB] markers (seq 10..30), 16 stale heartbeat(s) reported dropped`，`RESULT: PASS (18/18)`；紅路徑：主迴圈也走進 stall 點的暫時版本 `FAIL ... board reset at +4.2s after the stall`，`RESULT: FAIL (17/18)`，原始碼已還原、正式映像已重燒。
- 偏離與判斷（spec 沒寫的地方）：(1) Heartbeat 由獨立 sender 執行緒送出而非主迴圈直接送，因為 `bt_nus_send()` 在連結卡住時無界等待而主迴圈要餵狗；(2) 「1 s ± 200 ms」原樣用 PC 時鐘檢查，但此 PC 的無線鏈路有時把個別行延遲 0.3 至 2.4 s（板端 `uptime_ms` 間隔恆為 1000 ms），所以只有「PC 時鐘失敗、板端間隔精確、序號連續、任何一行不晚於前一行 3 s」時才重試視窗（最多 3 個視窗，細節寫 `link jitter`）；板端週期錯誤、缺號、重開機立即 FAIL；(3) `CentralConnection.open` 連線失敗最多重試 3 次（BlueZ 在鏈路差時 `failed to discover services` / `Unlikely Error`）；(4) Duty readback 改成以整週期計算（2 ms 視窗含約 40.3 個週期，純計數可差 1.25 %，`led set 128` 曾讀到 51.3 % 而超出 49 至 51 %），主機 suite 加 3 案，容差不變；(5) 順手修 ticket 08 的 `shell_nus.c` sequence-point 警告；(6) `[HB]` 標記依 `seq % 10 == 0`，所以主迴圈停滯逾 1 s 而跳過十的倍數時該標記會缺。
- 環境：2026-09-30 約 06:05 至 08:00 此 PC 的藍牙鏈路多次不穩（`reason=0x08`、連線時 discovery 失敗），ticket 08 的舊映像在同時段也 4 次全掉，不是 Heartbeat 造成；同一 adapter 上有已連線的 BLE 滑鼠（MX Master 3），是否為原因未證實。最終綠燈之前 `--flash` 曾有多次因此失敗。
- Review（embedded-review，兩位唯讀審查者）：Spec 審查指出 `uptime_ms` 在入隊時蓋章（改成 sender 送出時蓋章）、`near 0` 上限 10 太鬆（改 6）、重試視窗沒有上限（加 3 s 到達間隔上限）、stall 點不在 TX lock 內（移進 `shell_nus_notify()` 持鎖處）、缺「未訂閱不送」的 Harness Check（未補，屬設計保證，`bt_nus_send` 回 `-EINVAL`/`-ENOTCONN` 即丟棄，人工路徑無法在此 Harness 內不訂閱而連線）。Standards 審查無硬性違規；接受「TX buffer 256 bytes 以上的回覆可能被 Heartbeat 切開」（現行回覆皆為單短行，已寫入 `shell_nus.h`）、sender 堆疊 2048 已量測 640（`board-notes.md`）、優先權與佇列深度理由已寫進程式註解。
