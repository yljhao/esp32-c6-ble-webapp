// The Web App page (ticket 11): Web Bluetooth and DOM glue. All decisions (percent conversion,
// line reassembly and classification, command text, the slider send policy) are in logic.js and
// unit-tested there; this file is proven on the board by tools/webtest/board_web.py in real Chrome.
import {
  HEARTBEAT, LED, ERR, LED_GET_COMMAND, LatestWins, LineReassembler, brightnessToPercent,
  classifyLine, formatUptime, ledSetCommand, percentToBrightness,
} from './logic.js';

const NAME_PREFIX = 'XIAO-C6-LED';
const NUS_SERVICE = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const NUS_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';   // Central -> board (write)
const NUS_TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';   // board -> Central (notify)
const GET_REPLY_WAIT_MS = 3000;   // enable the slider anyway when the board does not answer `led get`

const $ = (id) => document.getElementById(id);
const el = {
  status: $('status'), connect: $('connect'), reconnect: $('reconnect'), disconnect: $('disconnect'),
  slider: $('slider'), sliderValue: $('slider-value'), board: $('board-brightness'), hbSeq: $('hb-seq'),
  hbUptime: $('hb-uptime'), hbNote: $('hb-note'), message: $('message'),
};

const reassembler = new LineReassembler();
const sender = new LatestWins();
let device = null;
let rx = null;
let generation = 0;        // bumped at every Connection, so a late callback of an old one is ignored
let expect = [];           // kinds of the commands sent, oldest first: each reply answers the first
let getTimer = null;

function setState(state, text) {
  el.status.dataset.state = state;
  el.status.textContent = text;
  // Connect (the chooser) only until a board has been chosen; from then on Reconnect reuses that device.
  const chosen = device !== null;
  el.connect.hidden = chosen;
  el.connect.disabled = state === 'connecting';
  el.reconnect.hidden = !chosen || state === 'connected';
  el.reconnect.disabled = state === 'connecting';
  el.disconnect.hidden = state !== 'connected';
}

function showMessage(text) { el.message.textContent = text; }

function showSlider(pct) {
  el.slider.value = String(pct);
  el.sliderValue.textContent = `${pct} %`;
}

async function write(text) {
  const bytes = new TextEncoder().encode(text);
  // With response when the characteristic has it: the acknowledgement paces a fast slider.
  if (rx.properties.write && rx.writeValueWithResponse) await rx.writeValueWithResponse(bytes);
  else if (rx.writeValueWithoutResponse) await rx.writeValueWithoutResponse(bytes);
  else await rx.writeValue(bytes);
}

async function sendCommand(kind, text) {
  const mine = generation;
  expect.push(kind);
  try {
    await write(text);
  } catch (e) {
    if (mine !== generation) return;
    expect.pop();
    showMessage(`Could not send "${text.trim()}": ${e.message}`);
  }
}

function requestGet() { return sendCommand('get', LED_GET_COMMAND); }

async function pumpSets(first) {
  const mine = generation;
  for (let value = first; value !== null; value = sender.done()) {
    await sendCommand('set', ledSetCommand(value));
    if (mine !== generation) return;
  }
}

function onLine(text) {
  const line = classifyLine(text);
  if (line.kind === HEARTBEAT) {
    el.hbSeq.textContent = String(line.seq);
    el.hbUptime.textContent = formatUptime(line.uptimeMs);
    el.hbNote.textContent = '';
    return;
  }
  if (line.kind !== LED && line.kind !== ERR) return;     // noise: nothing to show
  const kind = expect.shift();
  if (line.kind === LED) {
    el.board.textContent = `${line.brightness} (${brightnessToPercent(line.brightness)} %)`;
    if (kind === 'get') {
      showSlider(brightnessToPercent(line.brightness));
      clearTimeout(getTimer);
      el.slider.disabled = false;
    }
  } else {
    showMessage(`Board refused the command: ${line.message}`);
    if (kind === 'set') requestGet();      // learn what the board really holds
  }
}

// Counters the automated run reads to tell "no notification arrived" from "arrived but not shown".
window.__stats = { notifications: 0, lines: 0, times: [] };

function onNotification(event) {
  window.__stats.notifications++;
  for (const text of reassembler.feed(event.target.value)) {
    window.__stats.lines++;
    onLine(text);
  }
  window.__stats.times.push(Date.now());
}

function onDisconnected() {
  generation++;
  clearTimeout(getTimer);
  el.slider.disabled = true;
  // The Brightness is unknown until `led get` answers on the next Connection: show that, so a slider that
  // reads a value again has been re-synced from the board (and the automated run can tell).
  el.slider.value = '0';
  el.sliderValue.textContent = '-';
  el.board.textContent = '-';
  setState('disconnected', 'disconnected');
  // The last Heartbeat stays where it is; only a note says it is not live any more.
  if (/^[0-9]+$/.test(el.hbSeq.textContent)) el.hbNote.textContent = ' (last received, the Connection is down)';
  showMessage('Press Reconnect to connect to the same board again.');
}

async function openConnection() {
  const mine = ++generation;
  reassembler.reset();
  sender.reset();
  expect = [];
  setState('connecting', 'connecting...');
  showMessage('');
  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(NUS_SERVICE);
  rx = await service.getCharacteristic(NUS_RX);
  const tx = await service.getCharacteristic(NUS_TX);
  tx.addEventListener('characteristicvaluechanged', onNotification);
  await tx.startNotifications();
  if (mine !== generation) return;         // dropped while setting up: onDisconnected has spoken
  setState('connected', 'connected');
  getTimer = setTimeout(() => {
    showMessage('The board did not answer "led get"; the slider may not show its Brightness.');
    el.slider.disabled = false;
  }, GET_REPLY_WAIT_MS);
  await requestGet();
}

function failed(e) {
  setState('error', 'connection failed');
  showMessage(`${e.name}: ${e.message}`);
}

async function onConnectClick() {
  try {
    device = await navigator.bluetooth.requestDevice({
      filters: [{ namePrefix: NAME_PREFIX }],
      optionalServices: [NUS_SERVICE],
    });
    device.addEventListener('gattserverdisconnected', onDisconnected);
    await openConnection();
  } catch (e) {
    if (e.name === 'NotFoundError' && !device) {       // the user closed the chooser
      setState('idle', 'not connected');
      return;
    }
    failed(e);
  }
}

// Reconnect: the device object from the chooser is kept, so there is no chooser (spec: Web App).
async function onReconnectClick() {
  if (!device) return;
  try {
    await openConnection();
  } catch (e) {
    failed(e);
  }
}

el.connect.addEventListener('click', onConnectClick);
el.reconnect.addEventListener('click', onReconnectClick);
el.disconnect.addEventListener('click', () => { if (device && device.gatt.connected) device.gatt.disconnect(); });
el.slider.addEventListener('input', () => {
  const pct = Number(el.slider.value);
  el.sliderValue.textContent = `${pct} %`;
  const value = sender.request(percentToBrightness(pct));
  if (value !== null) pumpSets(value);
});

if (!('bluetooth' in navigator)) {
  setState('error', 'Web Bluetooth is not available in this browser');
  el.connect.disabled = true;
  showMessage('Use Chrome with chrome://flags/#enable-experimental-web-platform-features on, or Bluefy on iOS.');
}
