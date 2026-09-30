/*
 * Testing call: per Testing Decisions, webapp/logic.js gets a test in headless Chrome because it
 * is pure arithmetic (percent <-> 0-255) and the shared wire contract (line reassembly and
 * classification that tools/verify/central_logic.py mirrors on the Harness side).
 * Seam: the exported functions and LineReassembler of /webapp/logic.js.
 * Glue, proven on the board (tickets 11, 12): webapp/app.js (DOM, Web Bluetooth).
 * Expected values are literals from the spec's Wire contract and Brightness rules, or rows of
 * fixtures/wire_lines.json, which tools/verify/test_wire_fixtures.py checks against the Python side.
 *
 * Run: ./build.sh test-web   (tools/webtest/run.py serves the repo root and opens index.html).
 */
const tests = [];
const test = (name, fn) => tests.push({ name, fn });

function deepEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a), kb = Object.keys(b);
  return ka.length === kb.length && ka.every((k) => Object.hasOwn(b, k) && deepEqual(a[k], b[k]));
}
function eq(actual, expected, what = '') {
  if (!deepEqual(actual, expected)) {
    throw new Error(`${what}expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
function throws(fn, ErrorType, what = '') {
  try { fn(); } catch (e) {
    if (e instanceof ErrorType) return;
    throw new Error(`${what}threw ${e && e.name}, expected ${ErrorType.name}`);
  }
  throw new Error(`${what}did not throw`);
}

const fixtures = await (await fetch('/tools/webtest/fixtures/wire_lines.json')).json();
const toBytes = (chunk) => (typeof chunk === 'string' ? new TextEncoder().encode(chunk) : Uint8Array.from(chunk));

let logic;
try {
  logic = await import('/webapp/logic.js');
} catch (e) {
  logic = null;
  tests.push({ name: 'webapp/logic.js loads', fn() { throw new Error(String(e)); } });
}

// -- percent <-> Brightness (spec: Brightness rules) ------------------------------------------
if (logic) {
  const { percentToBrightness, brightnessToPercent } = logic;

  test('0 % -> 0, 50 % -> 128, 100 % -> 255', () => {
    eq(percentToBrightness(0), 0);
    eq(percentToBrightness(50), 128);
    eq(percentToBrightness(100), 255);
  });
  test('0 -> 0 %, 128 -> 50 %, 255 -> 100 %', () => {
    eq(brightnessToPercent(0), 0);
    eq(brightnessToPercent(128), 50);
    eq(brightnessToPercent(255), 100);
  });
  test('spot values: 1 % -> 3, 20 % -> 51, 99 % -> 252 and 1 -> 0 %, 64 -> 25 %, 254 -> 100 %', () => {
    eq(percentToBrightness(1), 3);
    eq(percentToBrightness(20), 51);
    eq(percentToBrightness(99), 252);
    eq(brightnessToPercent(1), 0);
    eq(brightnessToPercent(64), 25);
    eq(brightnessToPercent(254), 100);
  });
  test('an exact half rounds up: 10 % -> 26 (25.5), 30 % -> 77 (76.5), 90 % -> 230 (229.5)', () => {
    eq(percentToBrightness(10), 26);
    eq(percentToBrightness(30), 77);
    eq(percentToBrightness(90), 230);
  });
  test('every integer percent equals floor((2 * pct * 255 + 100) / 200) (integer-only oracle)', () => {
    for (let pct = 0; pct <= 100; pct++) {
      eq(percentToBrightness(pct), Math.floor((2 * pct * 255 + 100) / 200), `pct ${pct}: `);
    }
  });
  test('every Brightness 0-255 maps to a 0-100 percent that never falls as Brightness rises', () => {
    let last = -1;
    for (let n = 0; n <= 255; n++) {
      const p = brightnessToPercent(n);
      if (!(p >= 0 && p <= 100 && Number.isInteger(p))) throw new Error(`n ${n} -> ${p}`);
      if (p < last) throw new Error(`n ${n} -> ${p} after ${last}`);
      last = p;
    }
  });
  test('a percent the slider can pick converts to a Brightness the board accepts (0-255 integer)', () => {
    for (let pct = 0; pct <= 100; pct++) {
      const n = percentToBrightness(pct);
      if (!Number.isInteger(n) || n < 0 || n > 255) throw new Error(`pct ${pct} -> ${n}`);
    }
  });
  test('out-of-range or non-numeric input throws RangeError instead of becoming another Brightness', () => {
    for (const bad of [-1, 101, 100.5, NaN, Infinity, '50', null, undefined]) {
      throws(() => percentToBrightness(bad), RangeError, `percentToBrightness(${String(bad)}) `);
    }
    for (const bad of [-1, 256, 1.5, NaN, '128', null, undefined]) {
      throws(() => brightnessToPercent(bad), RangeError, `brightnessToPercent(${String(bad)}) `);
    }
  });
}

// -- line reassembly (spec: Wire contract, "a line may span several notifications") ---------------
if (logic) {
  const { LineReassembler } = logic;

  for (const fx of fixtures.reassemble) {
    test(`reassembly: ${fx.name}`, () => {
      const r = new LineReassembler();
      const got = fx.chunks.map((c) => r.feed(toBytes(c)));
      eq(got, fx.lines);
      eq(r.pending, fx.pending, 'pending: ');
    });
  }
  test('reassembly: chunk types Uint8Array, ArrayBuffer and DataView (what Web Bluetooth hands over) all work', () => {
    const bytes = new TextEncoder().encode('LED 3\n');
    eq(new LineReassembler().feed(bytes), ['LED 3']);
    eq(new LineReassembler().feed(bytes.buffer), ['LED 3']);
    eq(new LineReassembler().feed(new DataView(bytes.buffer)), ['LED 3']);
    // a DataView on a sub-range of a larger buffer sees only its own bytes
    const big = new Uint8Array([88, 88, ...bytes, 89]);
    eq(new LineReassembler().feed(new DataView(big.buffer, 2, bytes.length)), ['LED 3']);
  });
  test('reassembly: any split of a stream into two chunks gives the same lines', () => {
    const stream = new TextEncoder().encode('{"seq":5,"uptime_ms":5002}\nLED 128\nERR bad value\n');
    for (let cut = 0; cut <= stream.length; cut++) {
      const r = new LineReassembler();
      const got = [...r.feed(stream.slice(0, cut)), ...r.feed(stream.slice(cut))];
      eq(got, ['{"seq":5,"uptime_ms":5002}', 'LED 128', 'ERR bad value'], `cut ${cut}: `);
    }
  });
  test('reassembly: byte-at-a-time delivery gives the same lines', () => {
    const stream = new TextEncoder().encode('LED 1\nERR \u00e9\n');
    const r = new LineReassembler();
    const got = [];
    for (const b of stream) got.push(...r.feed(Uint8Array.of(b)));
    eq(got, ['LED 1', 'ERR \u00e9']);
  });
  test('reassembly: reset drops a partial line (a new Connection starts clean)', () => {
    const r = new LineReassembler();
    r.feed(toBytes('LED 1'));
    r.reset();
    eq(r.pending, '');
    eq(r.feed(toBytes('LED 2\n')), ['LED 2']);
  });
}

// -- line classification (spec: "a line beginning `{` is a Heartbeat; `LED ` or `ERR ` is a reply") -
if (logic) {
  const { classifyLine } = logic;

  for (const fx of fixtures.classify) {
    test(`classify ${JSON.stringify(fx.line)} -> ${fx.kind}`, () => {
      const got = classifyLine(fx.line);
      eq(got.kind, fx.kind, 'kind: ');
      eq(got.raw, fx.line, 'raw: ');
      eq(got.seq, fx.seq ?? null, 'seq: ');
      if (!fx.big_uptime) eq(got.uptimeMs, fx.uptime_ms ?? null, 'uptimeMs: ');
      eq(got.brightness, fx.brightness ?? null, 'brightness: ');
      eq(got.message, fx.message ?? null, 'message: ');
    });
  }
  test('classify: the largest uptime_ms (u64 max) is a Heartbeat with a finite number', () => {
    const got = classifyLine('{"seq":1,"uptime_ms":18446744073709551615}');
    eq(got.kind, 'heartbeat');
    if (!Number.isFinite(got.uptimeMs) || got.uptimeMs < 2 ** 63) throw new Error(`uptimeMs ${got.uptimeMs}`);
  });
  test('classify: a Heartbeat with extra keys or spaces still counts (JSON, as the Python side reads it)', () => {
    const got = classifyLine('{ "uptime_ms": 5, "seq": 2, "x": 1 }');
    eq([got.kind, got.seq, got.uptimeMs], ['heartbeat', 2, 5]);
  });
  test('classify: the seq inside a nested object is not the Heartbeat seq', () => {
    eq(classifyLine('{"a":{"seq":1,"uptime_ms":2}}').kind, 'other');
    eq(classifyLine('{"seq":1,"uptime_ms":2,"a":{"seq":9}}').seq, 1);
  });
  test('classify: a hundred thousand nested brackets is noise, not an exception', () => {
    eq(classifyLine('{"a":' + '['.repeat(100000)).kind, 'other');
    eq(classifyLine('{"a":' + '['.repeat(100000) + ']'.repeat(100000) + '}').kind, 'other');
  });
  test('classify: a line that claims a class but does not parse is not tried as the other class', () => {
    eq(classifyLine('{LED 5}').kind, 'other');
  });
  test('command encoding: led set <n> and led get end in exactly one newline', () => {
    eq(logic.ledSetCommand(0), 'led set 0\n');
    eq(logic.ledSetCommand(128), 'led set 128\n');
    eq(logic.ledSetCommand(255), 'led set 255\n');
    eq(logic.LED_GET_COMMAND, 'led get\n');
    for (const bad of [-1, 256, 1.5, NaN, '5', null]) {
      throws(() => logic.ledSetCommand(bad), RangeError, `ledSetCommand(${String(bad)}) `);
    }
  });
}

// -- slider send policy and uptime text (ticket 11) --------------------------------------------
// Testing call (ticket 11): LatestWins is slow-rules logic (a Web Bluetooth write cannot overlap
// another, and a dragged slider fires far faster than the link answers), so it is unit-tested;
// formatUptime is plain arithmetic. Expected values are literals.
if (logic) {
  const { LatestWins, formatUptime } = logic;

  test('LatestWins: the first request goes out at once', () => {
    const q = new LatestWins();
    eq(q.request(7), 7);
  });
  test('LatestWins: requests while one is in flight are held, only the newest survives', () => {
    const q = new LatestWins();
    eq(q.request(1), 1);
    eq(q.request(2), null);
    eq(q.request(3), null);
    eq(q.done(), 3);      // 2 was overtaken and never sent
    eq(q.done(), null);   // nothing more is waiting
  });
  test('LatestWins: after the queue drained a new request goes out at once again', () => {
    const q = new LatestWins();
    q.request(1);
    eq(q.done(), null);
    eq(q.request(2), 2);
  });
  test('LatestWins: a value equal to the one in flight is still sent after it (0 % twice is not a no-op)', () => {
    const q = new LatestWins();
    eq(q.request(5), 5);
    eq(q.request(5), null);
    eq(q.done(), 5);
  });
  test('LatestWins: 0 is a value, not "nothing"', () => {
    const q = new LatestWins();
    eq(q.request(1), 1);
    eq(q.request(0), null);
    eq(q.done(), 0);
  });
  test('LatestWins: reset drops the held value and the in-flight state (a new Connection)', () => {
    const q = new LatestWins();
    q.request(1);
    q.request(2);
    q.reset();
    eq(q.request(9), 9);
  });
  test('formatUptime: milliseconds as h:mm:ss.mmm', () => {
    eq(formatUptime(0), '0:00:00.000');
    eq(formatUptime(5702), '0:00:05.702');
    eq(formatUptime(48655), '0:00:48.655');
    eq(formatUptime(3600000 + 61001), '1:01:01.001');
    eq(formatUptime(100 * 3600000), '100:00:00.000');
  });
  test('formatUptime: a non-integer or negative input throws', () => {
    for (const bad of [-1, 1.5, NaN, '5', null]) throws(() => formatUptime(bad), RangeError, `formatUptime(${String(bad)}) `);
  });
}

// -- the module stays pure ---------------------------------------------------------------------
test('webapp/logic.js touches no DOM, Web Bluetooth, timer or other module (source scan)', async () => {
  const source = await (await fetch('/webapp/logic.js')).text();
  const code = source.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
  const hit = code.match(/\b(document|window|navigator|bluetooth|setTimeout|setInterval|fetch|localStorage|import)\b/i);
  if (hit) throw new Error(`found ${hit[0]}`);
});

// -- run and report ---------------------------------------------------------------------------
const results = [];
for (const { name, fn } of tests) {
  try { await fn(); results.push({ name, ok: true }); }
  catch (e) { results.push({ name, ok: false, detail: String(e && e.message || e) }); }
}
window.__results = results;
