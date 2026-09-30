# esp32-c6-ble-webapp

用網頁（Web Bluetooth）控制 Seeed Studio XIAO ESP32-C6 上橘色 User LED 亮度的參考範例，並即時顯示板子每秒送出的 Heartbeat。

- 韌體：Zephyr 4.4.2，目標板 `xiao_esp32c6/esp32c6/hpcore`，廣播名稱 `XIAO-C6-LED`，一次只接受一條 Connection。指令通道是 Zephyr shell 走 Nordic UART Service（ADR-0001），只放行 `led set` 與 `led get`。
- Web App：純 HTML、CSS 與 ES module JavaScript，無框架、無建置步驟，放在 `webapp/`，由 GitHub Actions 發佈到 GitHub Pages。
- 驗收 Harness：Python（`bleak` 當 Central、Playwright 驅動真實的 Google Chrome），在 PC 上無人值守跑完整條路徑（ADR-0004）。

Web App 網址：<https://yljhao.github.io/esp32-c6-ble-webapp/>（Pages 只發佈 `webapp/`，見 `.github/workflows/pages.yml`）。

名詞定義在 `CONTEXT.md`，設計決定在 `docs/adr/`，平台實測筆記在 `docs/agents/board-notes.md`。

## 環境

本專案是在下列環境驗證過的，`build.sh` 內寫死了這些路徑，換機器要自行改：

- Zephyr 4.4.2 在 `~/zephyrproject/zephyr`，Zephyr SDK 1.0.1 在 `~/zephyr-sdk-1.0.1`，west 用 `~/zephyrproject/.venv`。
- 板子接在 `/dev/ttyACM0`（USB-Serial/JTAG，`303a:1001`）；可用環境變數 `C6_PORT` 改。
- Harness 與網頁測試用專案自己的 `.venv`（`tools/venv.sh` 第一次執行時建立並安裝 `tools/requirements.txt`）。
- PC 需要 BlueZ 藍牙卡 `hci0`（Central 與 Chrome 不能同時使用同一張）與 Google Chrome（.deb，不是 snap Chromium，見 ADR-0002）。

## 燒錄

燒錄一律走本機的 esptool-build（`~/Desktop/Project/esptool-build`），不可安裝上游 esptool；`build.sh` 會先跑 guard，發現 PATH 上有別的 esptool 就拒絕（ADR-0003）。

```sh
./build.sh build                 # esptool guard + west build，輸出在 build/
west flash -d build              # 日常燒錄，晶片與連接埠自動偵測
./build.sh flash                 # 明確帶 --chip esp32c6 與 --port，Harness 與驗收用這個
./build.sh serial 15             # 重置後擷取 15 秒 console（帶時間戳記）
```

不要用 `west flash --no-reset`、`--erase`、`--esp-encrypt`，也不要用 sysbuild 或 MCUboot（ADR-0003）。

## 執行驗收 Harness

所有模式都不讀 stdin、不提問，最後一行是 `RESULT: PASS|FAIL`，只有 PASS 時結束碼為 0。

```sh
./verify.sh                      # 建置、確認晶片、重置、擷取 console 與 BLE Central 各項 Check（不燒錄）
./verify.sh --flash              # 同上，先燒錄剛建好的映像；完整驗收與回復 production 用這個
./verify.sh --web                # 真實 Chrome 開 webapp/（本機伺服器），與 console 交叉比對
./verify.sh --web --web-url URL  # 同一套流程，改測已發佈的網頁，例如上面的 Pages 網址
./verify.sh --bite               # 除錯映像：故意讓 watchdog 咬下去，結束後還原 production
./verify.sh --stall              # 除錯映像：讓 Heartbeat sender 卡住，結束後還原 production
./verify.sh --soak [N]           # 閒置 N 秒（預設 60）不得有任何重置
./build.sh test                  # 主機端測試（twister native_sim、guard、tools、Web App 邏輯），不碰板子
```

Harness 一次只讓一個工具碰板子（`/tmp/_dev_ttyACM0.lock`）。`--web` 用 Chrome 時 Harness 自己不開 Central。PC 的藍牙電波偶爾會讓 Connection 因 supervision timeout（`reason=0x08`）中斷；`--web` 遇到會自動重跑整個流程（最多 4 次），其他模式失敗時先看擷取記錄（`build/verify/`）裡是否有這個原因，再重跑一次。細節在 `docs/agents/board-notes.md`。

## 開啟 Chrome 的 Web Bluetooth

Linux 上的 Chrome 預設沒有 `navigator.bluetooth`，需要其中一種做法（ADR-0002，Chrome 154 驗證）：

- 開 `chrome://flags/#enable-experimental-web-platform-features`，設為 Enabled 後重新啟動 Chrome；或
- 用啟動旗標：`google-chrome --enable-experimental-web-platform-features`。

之後開啟 Web App，按 Connect，在選單選 `XIAO-C6-LED`。斷線後按 Reconnect 會直接沿用同一個裝置、不再跳出選單。自動化（`./verify.sh --web`）自己帶這個旗標並用 DevTools Protocol 回答選單，不需要人操作。

## 在 iPhone 的 Bluefy 開啟

Web Bluetooth 要求 HTTPS，所以把 Pages 網址 <https://yljhao.github.io/esp32-c6-ble-webapp/> 貼到 iOS 上 Bluefy 的網址列即可，不需要設定旗標。板子要在 production 狀態（`./verify.sh --flash` 結尾 `RESULT: PASS`）。

Bluefy 的實機驗收由使用者親自做（ticket 14：連線、拖曳滑桿看 LED 亮暗、Heartbeat 更新、關閉再開啟後重新連線），目前尚未執行，所以這份 README 對 Bluefy 上的行為不作任何保證。
