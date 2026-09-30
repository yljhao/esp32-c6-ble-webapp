// Pure logic of the Web App (spec: Wire contract, Brightness rules). No DOM, no Web Bluetooth,
// no timers: the page code (ticket 11 on) feeds notification bytes in and draws what comes out. Tested in headless
// Chrome by tools/webtest/run.py; tools/verify/central_logic.py is the Harness-side twin.

export const BRIGHTNESS_MAX = 255;
export const PERCENT_MAX = 100;

function assertBrightness(n) {
  if (!Number.isInteger(n) || n < 0 || n > BRIGHTNESS_MAX) {
    throw new RangeError(`brightness must be an integer from 0 to ${BRIGHTNESS_MAX}, got ${n}`);
  }
}

/** Slider percent (0-100) -> board Brightness: round(pct * 255 / 100), halves round up. */
export function percentToBrightness(pct) {
  if (typeof pct !== 'number' || !Number.isFinite(pct) || pct < 0 || pct > PERCENT_MAX) {
    throw new RangeError(`percent must be a number from 0 to ${PERCENT_MAX}, got ${pct}`);
  }
  return Math.round((pct * BRIGHTNESS_MAX) / PERCENT_MAX);
}

/** Board Brightness (integer 0-255) -> slider percent: round(n * 100 / 255). */
export function brightnessToPercent(n) {
  assertBrightness(n);
  return Math.round((n * PERCENT_MAX) / BRIGHTNESS_MAX);
}

// -- line reassembly ----------------------------------------------------------------------------

const NEWLINE = 0x0a;
const CARRIAGE_RETURN = 0x0d;
// ignoreBOM keeps a U+FEFF that is really in the data, as the Python twin does; invalid bytes
// become U+FFFD (fatal is off), never an exception.
const utf8 = new TextDecoder('utf-8', { ignoreBOM: true });

function toUint8Array(chunk) {
  if (chunk instanceof Uint8Array) return chunk;
  if (chunk instanceof ArrayBuffer) return new Uint8Array(chunk);
  if (ArrayBuffer.isView(chunk)) return new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength);
  throw new TypeError('a chunk must be a Uint8Array, an ArrayBuffer or a DataView');
}

/**
 * Turns NUS notification chunks into complete lines. A line ends with `\n` and may span several
 * notifications, or several lines may share one. A trailing `\r` is dropped. Bytes are buffered,
 * so a multi-byte UTF-8 character split between two notifications is decoded whole.
 */
export class LineReassembler {
  #buf = new Uint8Array(0);

  /** Add one notification's bytes; return the lines it completed, oldest first. */
  feed(chunk) {
    const bytes = toUint8Array(chunk);
    const joined = new Uint8Array(this.#buf.length + bytes.length);
    joined.set(this.#buf);
    joined.set(bytes, this.#buf.length);
    const lines = [];
    let start = 0;
    for (let i = joined.indexOf(NEWLINE); i !== -1; i = joined.indexOf(NEWLINE, start)) {
      let end = i;
      while (end > start && joined[end - 1] === CARRIAGE_RETURN) end--;
      lines.push(utf8.decode(joined.subarray(start, end)));
      start = i + 1;
    }
    this.#buf = joined.slice(start);
    return lines;
  }

  /** The unfinished line so far. */
  get pending() {
    return utf8.decode(this.#buf);
  }

  /** Drop a partial line, e.g. at a new Connection. */
  reset() {
    this.#buf = new Uint8Array(0);
  }
}

// -- line classification ------------------------------------------------------------------------

// Line kinds (spec: Wire contract). A line beginning `{` is a Heartbeat, one beginning `LED ` or
// `ERR ` is a reply; a line that claims a class but does not parse is OTHER.
export const HEARTBEAT = 'heartbeat';
export const LED = 'led';
export const ERR = 'err';
export const OTHER = 'other';

const SEQ_MAX = 0xffffffffn;
const UPTIME_MAX = 0xffffffffffffffffn;
// `-0` is a non-negative integer for Python's json.loads (it becomes 0), so it is one here too.
const UNSIGNED_DECIMAL = /^(?:-0|[0-9]+)$/;
// `LED <n>`: decimal 0-255, no sign, no leading zeros, single space, nothing after.
const LED_REPLY = /^LED (0|[1-9][0-9]{0,2})$/;
const ERR_PREFIX = 'ERR ';

/**
 * The raw text of each member of a JSON object's top level (the last one wins for a repeated key,
 * as in JSON.parse). `text` must already be valid JSON for an object. Needed because a Number
 * cannot tell 1.0 or 1e3 from 1, nor 2^64 from 2^64 - 1, and the wire contract wants integers.
 * (JSON.parse's reviver `context.source` would give the text more cheaply, but Bluefy's WebKit
 * may lack it; the Web App must run there.)
 */
function topLevelMembers(text) {
  const members = new Map();
  let i = text.indexOf('{') + 1;
  const skipSpace = () => { while (' \t\r\n'.includes(text[i])) i++; };
  const readString = () => {
    const from = i++;
    while (text[i] !== '"') i += text[i] === '\\' ? 2 : 1;
    return text.slice(from, ++i);
  };
  skipSpace();
  while (text[i] !== '}') {
    const key = JSON.parse(readString());
    skipSpace(); i++; skipSpace();               // the colon
    const from = i;
    for (let depth = 0; depth > 0 || (text[i] !== ',' && text[i] !== '}'); i++) {
      if (text[i] === '"') { readString(); i--; }
      else if (text[i] === '{' || text[i] === '[') depth++;
      else if (text[i] === '}' || text[i] === ']') depth--;
    }
    members.set(key, text.slice(from, i).trim());
    if (text[i] === ',') { i++; skipSpace(); }
  }
  return members;
}

function unsignedMember(members, key, max) {
  const token = members.get(key);
  if (token === undefined || !UNSIGNED_DECIMAL.test(token)) return null;
  return BigInt(token) <= max ? Math.abs(Number(token)) : null;
}

/**
 * `{"seq":<u32>,"uptime_ms":<u64>}` -> { seq, uptimeMs }, else null. uptimeMs is a Number, exact
 * up to 2^53 ms (285 thousand years); the u64 range is enforced on the text.
 */
export function parseHeartbeat(text) {
  let obj;
  try { obj = JSON.parse(text); } catch { return null; }
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) return null;
  const members = topLevelMembers(text);
  const seq = unsignedMember(members, 'seq', SEQ_MAX);
  const uptimeMs = unsignedMember(members, 'uptime_ms', UPTIME_MAX);
  return seq === null || uptimeMs === null ? null : { seq, uptimeMs };
}

/** `LED <n>` -> { ok: true, brightness: n, message: null }; `ERR <msg>` -> { ok: false, brightness: null, message }; else null. */
export function parseReply(text) {
  const m = LED_REPLY.exec(text);
  if (m) {
    const brightness = Number(m[1]);
    return brightness <= BRIGHTNESS_MAX ? { ok: true, brightness, message: null } : null;
  }
  if (text.startsWith(ERR_PREFIX)) return { ok: false, brightness: null, message: text.slice(ERR_PREFIX.length) };
  return null;
}

/** One reassembled line -> { kind, raw, seq, uptimeMs, brightness, message } (fields that do not apply are null). */
export function classifyLine(text) {
  const line = { kind: OTHER, raw: text, seq: null, uptimeMs: null, brightness: null, message: null };
  if (text.startsWith('{')) {
    const hb = parseHeartbeat(text);
    if (hb) return { ...line, kind: HEARTBEAT, seq: hb.seq, uptimeMs: hb.uptimeMs };
  } else {
    const reply = parseReply(text);
    if (reply) return { ...line, kind: reply.ok ? LED : ERR, brightness: reply.brightness, message: reply.message };
  }
  return line;
}

// -- commands (spec: Wire contract, Central -> board) --------------------------------------------

export const LED_GET_COMMAND = 'led get\n';

/** `led set <n>\n` for an integer 0-255; anything else throws, so a bad value never goes out. */
export function ledSetCommand(brightness) {
  assertBrightness(brightness);
  return `led set ${brightness}\n`;
}

// -- slider send policy (ticket 11) ---------------------------------------------------------------

/**
 * One Web Bluetooth write may be in flight at a time (a second one throws "GATT operation already
 * in progress"), and a dragged slider fires faster than the link answers. request() returns the
 * value to send now, or null when a write is in flight (the value is held; a newer one replaces
 * it). done() ends the write in flight and returns the held value to send next, or null.
 */
export class LatestWins {
  #busy = false;
  #held = null;

  request(value) {
    if (this.#busy) {
      this.#held = { value };
      return null;
    }
    this.#busy = true;
    return value;
  }

  done() {
    if (this.#held === null) {
      this.#busy = false;
      return null;
    }
    const { value } = this.#held;
    this.#held = null;      // stays busy: the caller sends `value` now
    return value;
  }

  /** Forget everything, e.g. at a new Connection. */
  reset() {
    this.#busy = false;
    this.#held = null;
  }
}

// -- uptime text ----------------------------------------------------------------------------------

/** Board uptime in ms (non-negative integer) -> `h:mm:ss.mmm`. */
export function formatUptime(ms) {
  if (!Number.isInteger(ms) || ms < 0) throw new RangeError(`uptime must be a non-negative integer, got ${ms}`);
  const pad = (n, width) => String(n).padStart(width, '0');
  const h = Math.floor(ms / 3600000);
  const m = Math.floor(ms / 60000) % 60;
  const s = Math.floor(ms / 1000) % 60;
  return `${h}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms % 1000, 3)}`;
}
