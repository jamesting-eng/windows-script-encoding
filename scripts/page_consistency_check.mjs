#!/usr/bin/env node
/**
 * page_consistency_check.mjs — compare the same selectors across a family of
 * pages and fail when they do not resolve to the same computed style.
 *
 * The failure this exists for: four pages reproduced from one template drift
 * apart one file at a time. The difference is usually invisible by eye
 * (a 2px font-size, a weight, a colour, a missing wrapper), and a screenshot
 * cannot prove equality — only computed values can.
 *
 * Usage:
 *   node page_consistency_check.mjs --base http://127.0.0.1:5173 \
 *     --pages blog/a.html,blog/b.html,blog/c.html \
 *     --selectors .article-eyebrow,.article-title,.article-meta
 *
 *   node page_consistency_check.mjs --base https://example.com --pages a.html,b.html \
 *     --selectors h1 --props fontSize,color --width 390        # mobile pass
 *
 *   node page_consistency_check.mjs ... --json                  # CI gate
 *
 * Exit codes: 0 all pages agree, 1 a difference was found, 2 environment
 * problem (no browser, Node too old, page did not load).
 *
 * Requirements: Node >= 22 (global WebSocket), Edge or Chrome installed.
 * Pure stdlib otherwise — nothing to npm install.
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const EXIT_OK = 0;
const EXIT_DIFF = 1;
const EXIT_ENV = 2;

function die(msg) {
  console.error(`[consistency] ${msg}`);
  process.exit(EXIT_ENV);
}

/* ----------------------------- arguments ----------------------------- */

function parseArgs(argv) {
  const out = { props: ["fontSize", "fontWeight", "color", "letterSpacing"], width: 1100, json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const take = () => {
      const v = argv[++i];
      if (v === undefined) die(`missing value for ${a}`);
      return v;
    };
    if (a === "--base") out.base = take().replace(/\/+$/, "");
    else if (a === "--pages") out.pages = take().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--selectors") out.selectors = take().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--props") out.props = take().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--width") out.width = Number(take());
    else if (a === "--height") out.height = Number(take());
    else if (a === "--browser") out.browser = take();
    else if (a === "--json") out.json = true;
    else if (a === "--help" || a === "-h") {
      console.log("usage: node page_consistency_check.mjs --base URL --pages a,b --selectors h1,.meta [--props ...] [--width N] [--json] [--browser PATH]");
      process.exit(EXIT_OK);
    } else die(`unknown argument: ${a}`);
  }
  if (!out.base) die("--base is required (e.g. --base http://127.0.0.1:5173)");
  if (!out.pages || out.pages.length < 2) die("--pages needs at least two pages to compare");
  if (!out.selectors || !out.selectors.length) die("--selectors is required");
  return out;
}

/* ----------------------------- browser ----------------------------- */

function findBrowser(explicit) {
  // An explicit path that does not exist is a typo or a stale config — say so
  // instead of silently falling back to another browser (the user would then
  // trust a measurement taken by something they did not choose).
  if (explicit) {
    try {
      if (fs.statSync(explicit).isFile()) return explicit;
    } catch {}
    die(`--browser path does not exist: ${explicit}`);
  }
  const candidates = [
    process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  for (const c of candidates) {
    try {
      if (fs.statSync(c).isFile()) return c;
    } catch {}
  }
  die(
    "no browser found. Pass --browser <path to chrome/edge>, or set CHROME_PATH.\n" +
      "         Tried:\n" +
      candidates.map((c) => `           ${c}`).join("\n")
  );
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getJson(url, tries = 40) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(1500) });
      if (r.ok) return await r.json();
    } catch {}
    await sleep(250);
  }
  die(`browser debugging endpoint never answered: ${url}`);
}

class CDP {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.pending = new Map();
    this.ws.addEventListener("message", (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id);
        this.pending.delete(m.id);
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
      }
    });
  }
  ready() {
    return new Promise((res, rej) => {
      this.ws.addEventListener("open", res);
      this.ws.addEventListener("error", () => rej(new Error("websocket error")));
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
  async eval(expr) {
    const r = await this.send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
    return r.result.value;
  }
  close() {
    try {
      this.ws.close();
    } catch {}
  }
}

/* ----------------------------- measurement ----------------------------- */

const PROBE = (selectors, props) => `(async () => {
  if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) {} }
  const props = ${JSON.stringify(props)};
  const out = {};
  for (const sel of ${JSON.stringify(selectors)}) {
    const el = document.querySelector(sel);
    if (!el) { out[sel] = null; continue; }
    const cs = getComputedStyle(el);
    const row = {};
    for (const p of props) row[p] = cs[p];
    row.__count = document.querySelectorAll(sel).length;
    row.__text = (el.textContent || "").trim().slice(0, 40);
    out[sel] = row;
  }
  return JSON.stringify(out);
})()`;

async function main() {
  if (typeof WebSocket !== "function") {
    die(`Node ${process.version} has no global WebSocket — this script needs Node >= 22.`);
  }
  const opt = parseArgs(process.argv.slice(2));
  const browser = findBrowser(opt.browser);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "pgcons-"));
  const port = 9400 + Math.floor(Math.random() * 400);

  const child = spawn(
    browser,
    [
      "--headless=new",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-gpu",
      "--hide-scrollbars",
      "about:blank",
    ],
    { stdio: "ignore", windowsHide: true }
  );

  let cdp;
  try {
    const ver = await getJson(`http://127.0.0.1:${port}/json/version`);
    const list = await getJson(`http://127.0.0.1:${port}/json/list`);
    const target = list.find((t) => t.type === "page");
    if (!target) die("browser started but exposed no page target");
    cdp = new CDP(target.webSocketDebuggerUrl);
    await cdp.ready();
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Network.enable");
    // A stale stylesheet silently answers with yesterday's values, which reads
    // as "everything agrees" — the one failure mode a consistency check must
    // not have.
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    const height = opt.height || Math.round(opt.width * 0.8);
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: opt.width,
      height,
      deviceScaleFactor: 1,
      mobile: opt.width < 700,
    });

    const measured = [];
    for (const page of opt.pages) {
      const url = page.startsWith("http") ? page : `${opt.base}/${page.replace(/^\/+/, "")}`;
      await cdp.send("Page.navigate", { url });
      await sleep(700);
      const state = await cdp.eval(
        `JSON.stringify({ ready: document.readyState, title: document.title, href: location.href })`
      );
      const st = JSON.parse(state);
      if (st.ready !== "complete") die(`${url} did not finish loading (readyState=${st.ready})`);
      const rows = JSON.parse(await cdp.eval(PROBE(opt.selectors, opt.props)));
      measured.push({ page, url: st.href, rows });
    }

    /* ----------------------------- compare ----------------------------- */
    const diffs = [];
    const summary = [];

    for (const sel of opt.selectors) {
      const perProp = {};
      let missing = 0;
      for (const m of measured) {
        const row = m.rows[sel];
        if (!row) {
          missing++;
          continue;
        }
        for (const p of opt.props) {
          (perProp[p] ||= []).push({ page: m.page, value: row[p] });
        }
      }
      if (missing) {
        diffs.push({
          selector: sel,
          prop: "(exists)",
          detail: measured.filter((m) => !m.rows[sel]).map((m) => m.page),
          message: `selector not found on ${missing}/${measured.length} pages`,
        });
      }
      for (const p of opt.props) {
        const rows = perProp[p] || [];
        if (!rows.length) continue;
        const values = [...new Set(rows.map((r) => r.value))];
        if (values.length > 1) {
          diffs.push({
            selector: sel,
            prop: p,
            detail: rows.map((r) => `${r.page}=${r.value}`),
            message: `${values.length} distinct values`,
          });
        }
      }
      const base = measured[0].rows[sel];
      if (base) {
        summary.push({
          selector: sel,
          baseline: Object.fromEntries(opt.props.map((p) => [p, base[p]])),
          count: base.__count,
          text: base.__text,
        });
      }
    }

    if (opt.json) {
      console.log(
        JSON.stringify(
          {
            base: opt.base,
            width: opt.width,
            pages: measured.map((m) => m.page),
            selectors: opt.selectors,
            props: opt.props,
            baseline: summary,
            differences: diffs,
            verdict: diffs.length ? "FAIL" : "PASS",
          },
          null,
          2
        )
      );
    } else {
      console.log(`[consistency] ${measured.length} pages x ${opt.selectors.length} selectors @ ${opt.width}px`);
      for (const s of summary) {
        console.log(`  ${s.selector}  (x${s.count} on page 1)`);
        console.log(`    ${opt.props.map((p) => `${p}=${s.baseline[p]}`).join("  ")}`);
      }
      if (diffs.length) {
        console.log("");
        console.log(`[consistency] FAIL — ${diffs.length} difference(s):`);
        for (const d of diffs) {
          console.log(`  · ${d.selector} / ${d.prop}: ${d.message}`);
          for (const line of d.detail) console.log(`      ${line}`);
        }
        console.log("");
        console.log("[consistency] A screenshot cannot prove equality. These are computed values.");
      } else {
        console.log("");
        console.log(`[consistency] PASS — every page resolves every selector to the same values.`);
      }
    }

    cdp.close();
    return diffs.length ? EXIT_DIFF : EXIT_OK;
  } finally {
    try {
      child.kill();
    } catch {}
    await sleep(150);
    try {
      fs.rmSync(profile, { recursive: true, force: true });
    } catch {}
  }
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(`[consistency] ${err && err.stack ? err.stack : err}`);
    process.exit(EXIT_ENV);
  });
