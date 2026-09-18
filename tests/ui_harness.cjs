/* Gate 0 UI harness: runs codebase/ui.html <script> in node:vm with a fake DOM.
 * Proves: no dynamic HTML sinks execute payloads, flows run error-free,
 * API errors never fabricate AI replies. Exit 0 + JSON summary on stdout.
 */
const fs = require("fs");
const vm = require("vm");

const htmlPath = process.argv[2];
const html = fs.readFileSync(htmlPath, "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const script = scripts[scripts.length - 1][1];

const PAYLOAD = "<img src=x onerror=window.__pwned=1>";
const results = {};
const consoleErrors = [];
const alerts = [];
const allEls = [];
const innerHTMLSets = [];
const createdTags = [];

class FakeClassList {
  constructor() { this._s = new Set(); }
  add(...c) { c.forEach((x) => this._s.add(x)); }
  remove(...c) { c.forEach((x) => this._s.delete(x)); }
  toggle(c, f) {
    if (f === undefined) f = !this._s.has(c);
    if (f) this._s.add(c); else this._s.delete(c);
    return f;
  }
  contains(c) { return this._s.has(c); }
}

class FakeEl {
  constructor(tag) {
    this.tagName = String(tag || "div").toUpperCase();
    createdTags.push(this.tagName);
    allEls.push(this);
    this.children = [];
    this._text = "";
    this._html = "";
    this.listeners = {};
    this.attributes = {};
    this.style = {};
    this.dataset = {};
    this.classList = new FakeClassList();
    this.className = "";
    this.id = "";
    this.value = "";
    this.title = "";
    this.type = "";
    this.disabled = false;
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.offsetTop = 0;
    this.removed = false;
  }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text; }
  set innerHTML(v) {
    innerHTMLSets.push({ id: this.id, tag: this.tagName, value: String(v) });
    this._html = String(v);
    this.children = [];
  }
  get innerHTML() { return this._html; }
  appendChild(c) { this.children.push(c); return c; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  removeEventListener() {}
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
  remove() { this.removed = true; }
  focus() {}
  click() { (this.listeners.click || []).forEach((f) => f({ preventDefault() {}, stopPropagation() {} })); }
  scrollTo() {}
  scrollBy() {}
  scrollIntoView() {}
  querySelectorAll() { return []; }
  querySelector() { return null; }
}

const elsById = {};
function getEl(id) {
  if (!elsById[id]) { const e = new FakeEl("div"); e.id = id; elsById[id] = e; }
  return elsById[id];
}

let fetchImpl = () => Promise.reject(new Error("no stub"));
const sandbox = {
  console: { ...console, error: (...a) => { consoleErrors.push(a.map(String).join(" ")); } },
  document: {
    getElementById: getEl,
    createElement: (t) => new FakeEl(t),
    createTextNode: (t) => { const e = new FakeEl("#text"); e._text = String(t); return e; },
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener: () => {},
  },
  window: { addEventListener: () => {}, scrollTo: () => {} },
  navigator: { clipboard: { writeText: async () => {} } },
  alert: (m) => alerts.push(String(m)),
  confirm: () => true,
  fetch: (...a) => fetchImpl(...a),
  setTimeout, clearTimeout,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function okResp(data) { return { ok: true, json: async () => data, text: async () => JSON.stringify(data) }; }
function failResp() { return { ok: false, status: 404, json: async () => ({}), text: async () => "no" }; }
const flush = (n = 6) => (async () => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); })();

function aggText(id) {
  const root = getEl(id);
  const parts = [];
  (function walk(e) { parts.push(e._text || ""); (e.children || []).forEach(walk); })(root);
  return parts.join("\n");
}
function payloadInHTML() {
  return innerHTMLSets.filter((s) => s.value.includes("<img") || s.value.includes("onerror=") || s.value.includes(PAYLOAD));
}
function checkNoExec(label) {
  const bad = payloadInHTML();
  const img = createdTags.filter((t) => t === "IMG");
  if (bad.length || img.length || sandbox.window.__pwned) {
    throw new Error(`${label}: exec sink (html=${bad.length}, img=${img.length}, pwned=${!!sandbox.window.__pwned})`);
  }
}

const driver = `
;globalThis.__run = async () => {
  const R = {};
  const flush = ${flush.toString()};
  const PAY = ${JSON.stringify(PAYLOAD)};
  const fileJSON = { path: "src/app.py", content: "a=1\\nprint(a)\\n", total_lines: 2, sha256: "abcdef1234567890abcdef", symbols: [{ name: "f", kind: "function", line: 1, end_line: 2 }] };

  // S1: init with stubbed backend
  try {
    globalThis.__fetchImpl = (url) => {
      const u = String(url);
      if (u.includes("/api/manifest")) return Promise.resolve({ ok: true, json: async () => ({ files: [] }), text: async () => "" });
      if (u.includes("/api/provider-status")) return Promise.resolve({ ok: true, json: async () => ({ status: "mock", openai: false, gemini: false }), text: async () => "" });
      if (u.includes("/api/file")) return Promise.resolve({ ok: true, json: async () => fileJSON, text: async () => "" });
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" });
    };
    init();
    await flush();
    R.init_no_errors = { pass: true };
  } catch (e) { R.init_no_errors = { pass: false, detail: String(e && e.message || e) }; }

  // S2: chat XSS
  try {
    chatHistory = { mentor: [
      { role: "user", text: PAY },
      { role: "ai", text: PAY, notes: [{ label: "N:", text: PAY }], badges: [{ label: PAY, title: PAY, path: PAY, line: 1 }] },
    ], pairpal: [] };
    coachTab = "mentor";
    renderChat();
    const t = document.getElementById("chat-messages");
    let own = [];
    (function walk(e) { if ((e._text || "").includes(PAY)) own.push(e.tagName); (e.children || []).forEach(walk); })(t);
    if (!own.length) throw new Error("payload not rendered as text");
    // badge with non-allowlisted path must be a no-op, never throw
    const btns = [];
    (function walk(e) { if (e.tagName === "BUTTON") btns.push(e); (e.children || []).forEach(walk); })(t);
    btns.forEach((b) => b.click());
    await flush();
    R.xss_chat = { pass: true };
  } catch (e) { R.xss_chat = { pass: false, detail: String(e && e.message || e) }; }

  // S3: provenance XSS (allowlisted path, malicious symbol)
  try {
    currentManifestFiles = [{ p: "src/app.py", cat: "code", l: 9, h: "ab", full_sha: "ab", sym: [PAY] }];
    renderProvenanceList(currentManifestFiles);
    const t = document.getElementById("prov-list-container");
    let own = [];
    (function walk(e) { if ((e._text || "").includes(PAY)) own.push(e.tagName); (e.children || []).forEach(walk); })(t);
    if (!own.length) throw new Error("symbol payload not rendered as text");
    const tags = [];
    (function walk(e) { if (e.tagName === "SPAN" && (e.className || "").includes("lp-ast-tag")) tags.push(e); (e.children || []).forEach(walk); })(t);
    if (!tags.length) throw new Error("no ast tag rendered");
    tags[0].click();
    await flush();
    R.xss_prov = { pass: true };
  } catch (e) { R.xss_prov = { pass: false, detail: String(e && e.message || e) }; }

  // S4: code viewer XSS
  try {
    renderFileContent("src/app.py", "ok\\n" + PAY + "\\n", 3, "abcdef1234567890", [{ name: PAY, kind: "function", line: 2 }], 2, null);
    const t = document.getElementById("code-table");
    let own = 0;
    (function walk(e) { if ((e._text || "").includes(PAY)) own++; (e.children || []).forEach(walk); })(t);
    if (!own) throw new Error("code payload not rendered as text");
    renderFileContent("src/app.py", "ok\\n", 1, "chưa xác minh", [], null, null);
    if (document.getElementById("code-modal-verify")._text !== "⚠ chưa xác minh") throw new Error("unverified label missing");
    R.xss_code = { pass: true };
  } catch (e) { R.xss_code = { pass: false, detail: String(e && e.message || e) }; }

  // S5: chips with quotes/payload
  try {
    ROUNDS_DATA[0].chips = [PAY, "a'b\\"c"];
    currentRoundIdx = 0;
    renderChips();
    const row = document.getElementById("chips-row");
    const btns = row.children.filter((c) => c.tagName === "BUTTON");
    if (btns.length !== 2 || btns[0]._text !== PAY) throw new Error("chip text mismatch");
    R.xss_chips = { pass: true };
  } catch (e) { R.xss_chips = { pass: false, detail: String(e && e.message || e) }; }

  // S6: flows without console errors
  try {
    toggleLeftPanel(); toggleLeftPanel();
    setMobileView("docs"); setMobileView("center"); setMobileView("metrics");
    setProvFilter("code");
    document.getElementById("prov-search").value = "app";
    filterProvList();
    selectedOpt = null;
    submitDecision();
    selectCard(ROUNDS_DATA[0].options[0]);
    submitDecision();
    const h = document.getElementById("history-log");
    if (!h.children.length) throw new Error("history empty after submit");
    inspectFile("src/app.py", 1, "");
    await flush();
    jumpToLine(1);
    scrollCodeViewer("pgdn"); scrollCodeViewer("home");
    setCoachTab("pairpal"); setCoachTab("mentor");
    resetSim();
    R.flows = { pass: true };
  } catch (e) { R.flows = { pass: false, detail: String(e && e.message || e) }; }

  // S7: QA ok with payload answer
  try {
    globalThis.__fetchImpl = (url) => {
      if (String(url).includes("/api/qa")) return Promise.resolve({
        ok: true,
        json: async () => ({ answer: "Ans " + PAY, citations_detail: [{ ref: "src/app.py:36-75", path: "src/app.py", start_line: 36, chunk_id: "src/app.py:36-75", sha_short: "ab12" }], evidence: [], provider_status: "mock", retrieved_count: 1 }),
        text: async () => "",
      });
      if (String(url).includes("/api/file")) return Promise.resolve({ ok: true, json: async () => fileJSON, text: async () => "" });
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" });
    };
    document.getElementById("qa-input").value = "Q?";
    await sendQAPrompt();
    await flush();
    const t = document.getElementById("qa-response");
    let agg = [];
    (function walk(e) { agg.push(e._text || ""); (e.children || []).forEach(walk); })(t);
    if (!agg.join("\\n").includes(PAY)) throw new Error("qa answer not rendered as text");
    const btns = [];
    (function walk(e) { if (e.tagName === "BUTTON") btns.push(e); (e.children || []).forEach(walk); })(t);
    if (!btns.length) throw new Error("no citation badge");
    btns[0].click();
    await flush();
    if (document.getElementById("code-modal-title")._text !== "src/app.py") throw new Error("badge did not open file");
    R.qa_ok = { pass: true };
  } catch (e) { R.qa_ok = { pass: false, detail: String(e && e.message || e) }; }

  // S8: API error must not fabricate an AI reply
  try {
    globalThis.__fetchImpl = () => Promise.reject(new Error("down"));
    chatHistory = { mentor: [], pairpal: [] };
    coachTab = "mentor";
    document.getElementById("dock-input").value = "Q?";
    const aiBefore = 0;
    sendPrompt();
    await flush(10);
    const msgs = chatHistory.mentor;
    const aiAfter = msgs.filter((m) => m.role === "ai").length;
    const last = msgs[msgs.length - 1];
    if (aiAfter !== aiBefore) throw new Error("fabricated AI reply on transport error");
    if (!last || last.role !== "status" || !String(last.text).includes("Không thể kết nối")) throw new Error("missing retry status");
    if (document.getElementById("dock-input").value !== "Q?") throw new Error("question not kept for resend");
    R.api_error_no_fake_ai = { pass: true };
  } catch (e) { R.api_error_no_fake_ai = { pass: false, detail: String(e && e.message || e) }; }

  // S9: provider badge honesty (KEY, never LIVE claim)
  try {
    globalThis.__fetchImpl = (url) => Promise.resolve({ ok: true, json: async () => ({ status: "live_openai", openai: true, gemini: false }), text: async () => "" });
    await checkProviderStatus();
    await flush();
    const t = document.getElementById("qa-provider-status")._text;
    if (!t.includes("KEY") || t.includes("LIVE")) throw new Error("dishonest badge: " + t);
    R.badge_honesty = { pass: true };
  } catch (e) { R.badge_honesty = { pass: false, detail: String(e && e.message || e) }; }

  return R;
};
`;

(async () => {
  try {
    sandbox.__fetchImpl = null;
    sandbox.fetch = (...a) => sandbox.__fetchImpl(...a);
    vm.runInContext(script + driver, sandbox);
    const R = await vm.runInContext("__run()", sandbox);
    // global exec-sink audit across all scenarios
    const bad = innerHTMLSets.filter(
      (s) => s.value.includes("<img") || s.value.includes("onerror=") || s.value.includes(PAYLOAD)
    );
    const img = createdTags.filter((t) => t === "IMG");
    R.no_exec_sink = bad.length || img.length || sandbox.window.__pwned
      ? { pass: false, detail: `html=${bad.length} img=${img.length}` }
      : { pass: true };
    R.no_console_errors = consoleErrors.length
      ? { pass: false, detail: consoleErrors.slice(0, 3).join(" | ") }
      : { pass: true };
    console.log(JSON.stringify({ scenarios: R, alerts: alerts.slice(0, 5) }));
  } catch (e) {
    console.log(JSON.stringify({ harness_error: String((e && e.stack) || e) }));
    process.exitCode = 2;
  }
})();
