// Browser tests for Sahaya, written like a manual tester's checklist.
// Starts the backend in offline fake mode (no keys, no real money) and the built frontend,
// then drives Chrome through real journeys on desktop and phone sizes.
//
//   cd tests-ui && npm install && npx playwright install chromium && npm test
import { spawn, execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const API = "http://127.0.0.1:8010";
const WEB = "http://localhost:5180";
const PY = process.env.SAHAYA_PYTHON || path.join(ROOT, "backend", ".venv", "bin", "python");
const AXE = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "node_modules/axe-core/axe.min.js"), "utf8");

const results = [];
let backend;

function startBackend() {
  backend = spawn(PY, ["-m", "uvicorn", "app.main:app", "--port", "8010", "--log-level", "warning"], {
    cwd: path.join(ROOT, "backend"),
    env: { ...process.env, SAHAYA_FAKE: "1", FRONTEND_URL: WEB, BACKEND_URL: API, DOTENV_DISABLED: "1" },
    stdio: "ignore",
  });
}
const stopBackend = () => backend && backend.kill();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(url, ms = 20000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await sleep(300);
  }
  throw new Error(`timeout waiting for ${url}`);
}

async function check(name, fn) {
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`  ✓ ${name}`);
  } catch (e) {
    results.push({ name, ok: false, err: e.message.split("\n")[0] });
    console.log(`  ✗ ${name}\n      ${e.message.split("\n")[0]}`);
  }
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg); };

async function freshPage(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, ...opts });
  await ctx.addInitScript(() => {
    // fresh session each time, and no real speech in headless runs
    try { if (!sessionStorage.getItem("t")) { localStorage.clear(); sessionStorage.setItem("t", "1"); } } catch {}
    window.speechSynthesis && (window.speechSynthesis.speak = () => {});
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => { page.jsErrors = (page.jsErrors || []).concat(e.message); });
  return page;
}
async function type(page, text) {
  await page.fill("#say", text);
  await page.press("#say", "Enter");
  await page.waitForFunction(() => !document.querySelector("#say").disabled, null, { timeout: 15000 });
}
const lead = (page) => page.textContent(".lead");

async function axe(page, label) {
  await page.addScriptTag({ content: AXE });
  const res = await page.evaluate(async () => await window.axe.run(document, { resultTypes: ["violations"] }));
  const bad = res.violations.filter((v) => ["serious", "critical"].includes(v.impact));
  expect(bad.length === 0, `${label}: ${bad.map((v) => `${v.id} (${v.nodes.length})`).join(", ")}`);
}

// ---------------------------------------------------------------------------------------------

console.log("Building frontend for test…");
execSync(`npx vite build --outDir dist-test --emptyOutDir`, {
  cwd: path.join(ROOT, "frontend"), env: { ...process.env, VITE_API_URL: API }, stdio: "ignore",
});
const preview = spawn("npx", ["vite", "preview", "--outDir", "dist-test", "--port", "5180", "--strictPort"], {
  cwd: path.join(ROOT, "frontend"), stdio: "ignore",
});
await waitFor(WEB);
const browser = await chromium.launch();

try {
  console.log("\nCold start (server asleep)");
  await check("shows 'Waking up' while the server is asleep, then connects by itself", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB);
    await page.waitForSelector("text=Waking up Sahaya", { timeout: 6000 });
    expect(await page.isDisabled("button[type=submit]"), "Send should be disabled while connecting");
    startBackend();
    await page.waitForSelector(".rules", { timeout: 30000 });
    expect(!(await page.isVisible("text=Waking up Sahaya")), "banner should disappear once connected");
    await page.context().close();
  });

  console.log("\nHappy path");
  await check("search shows 3 numbered options and reads them", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await type(page, "anything useful");
    expect((await page.$$(".product")).length === 3, "expected 3 options");
    expect((await lead(page)).includes("Option 1"), "reply should mention Option 1");
    await page.context().close();
  });

  await check("choose option, say yes, PayPal opens, come back paid, refund", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await type(page, "anything useful");
    await page.click("text=Choose option 1");
    await page.waitForSelector("text=Ready to pay");
    await type(page, "yes");
    await page.waitForURL(/\/done\?pid=.*result=paid/, { timeout: 10000 });
    expect((await page.textContent("h1")).includes("Payment complete"), "done page should say complete");
    await page.click("text=Back to Sahaya");
    await page.waitForSelector("text=Ask for a refund");
    await page.click("text=Ask for a refund");
    await page.waitForSelector(".panel h2:has-text('Refunded')");
    expect(!page.jsErrors, `JS errors: ${page.jsErrors}`);
    await page.context().close();
  });

  console.log("\nYes, no, typos");
  for (const [answer, outcome] of [["yse", "paid"], ["Yes please!", "paid"], ["no thanks", "cancelled"],
    ["nope", "cancelled"], ["yes but cheaper", "still ready"]]) {
    await check(`answer "${answer}" → ${outcome}`, async () => {
      const page = await freshPage(browser);
      await page.goto(WEB); await page.waitForSelector(".rules");
      await type(page, "anything useful");
      await page.click("text=Choose option 2");
      await page.waitForSelector("text=Ready to pay");
      await page.fill("#say", answer); await page.press("#say", "Enter");
      if (outcome === "paid") {
        await page.waitForURL(/result=paid/, { timeout: 10000 });
      } else if (outcome === "cancelled") {
        await page.waitForSelector(".panel h2:has-text('Cancelled')", { timeout: 8000 });
        expect((await lead(page)).includes("Nothing was paid"), "should say nothing was paid");
      } else {
        await page.waitForFunction(() => !document.querySelector("#say").disabled);
        expect(page.url().startsWith(WEB) && !page.url().includes("done"), "must not go to PayPal");
      }
      await page.context().close();
    });
  }

  console.log("\nTrusted contact");
  await check("over 50 dollars waits for family; approval in another tab unlocks it", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await type(page, "anything useful");
    await page.click("text=Choose option 3");
    await page.waitForSelector("text=Waiting for your trusted contact");
    await type(page, "yes");
    expect((await lead(page)).includes("still waiting"), "yes before approval must not pay");
    const [family] = await Promise.all([page.context().waitForEvent("page"), page.click("text=Open trusted contact view")]);
    await family.waitForSelector("text=A purchase needs your approval");
    await family.click("button:has-text('Approve')");
    await family.waitForSelector("text=Approved");
    await page.waitForSelector("text=Ready to pay", { timeout: 8000 });
    expect((await lead(page)).includes("approved"), "should announce the approval");
    await page.context().close();
  });

  await check("family decline is announced and nothing is paid", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await type(page, "anything useful");
    await page.click("text=Choose option 3");
    const [family] = await Promise.all([page.context().waitForEvent("page"), page.click("text=Open trusted contact view")]);
    await family.click("button:has-text('Decline')");
    await page.waitForSelector(".panel h2:has-text('said no')", { timeout: 8000 });
    await page.context().close();
  });

  await check("family link with a bad id shows a clear error", async () => {
    const page = await freshPage(browser);
    await page.goto(`${WEB}/family?pid=doesnotexist`);
    await page.waitForSelector("[role=alert]");
    await page.context().close();
  });

  console.log("\nSafety demo");
  await check("a listing with hidden instructions is left out and explained", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await page.click("summary:has-text('Safety demo')");
    await page.check(".demo input[type=checkbox]");
    await type(page, "a kettle");
    await page.waitForSelector("text=tried to trick me");
    const titles = await page.$$eval(".product-title", (els) => els.map((e) => e.textContent));
    expect(!titles.some((t) => t.includes("SIMULATED")), "fake listing must never be offered");
    await page.context().close();
  });

  console.log("\nKeyboard and screen reader");
  await check("first Tab lands on 'Skip to talk', which moves focus to the composer", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await page.keyboard.press("Tab");
    const first = await page.evaluate(() => document.activeElement.outerHTML.slice(0, 80));
    expect(first.includes("Skip to talk"), `first focus was ${first}`);
    await page.keyboard.press("Enter");
    await page.keyboard.press("Tab");
    const next = await page.evaluate(() => document.activeElement.id || document.activeElement.className);
    expect(["talk", "say"].some((k) => String(next).includes(k)), `after skip, focus went to ${next}`);
    await page.context().close();
  });

  await check("whole purchase works with keyboard only", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await page.focus("#say");
    await page.keyboard.type("anything useful"); await page.keyboard.press("Enter");
    await page.waitForSelector(".product");
    await page.focus("text=Choose option 1"); await page.keyboard.press("Enter");
    await page.waitForSelector("text=Ready to pay");
    await page.focus(".btn-pay"); await page.keyboard.press("Enter");
    await page.waitForURL(/result=paid/, { timeout: 10000 });
    await page.context().close();
  });

  await check("typing a space in the box types a space (doesn't trigger the mic)", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await page.focus("#say"); await page.keyboard.type("a b");
    expect((await page.inputValue("#say")) === "a b", "space must type");
    await page.context().close();
  });

  await check("replies are announced (aria-live) and buttons have names", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    expect((await page.getAttribute(".lead", "aria-live")) === "polite", "lead should be aria-live");
    expect(!!(await page.getAttribute(".talk", "aria-label")), "talk button needs a label");
    await page.context().close();
  });

  for (const scheme of ["light", "dark"]) {
    await check(`no serious accessibility violations (axe, ${scheme} mode, with purchase panel)`, async () => {
      const page = await freshPage(browser, { colorScheme: scheme });
      await page.goto(WEB); await page.waitForSelector(".rules");
      await type(page, "anything useful");
      await page.click("text=Choose option 3");
      await page.waitForSelector(".panel");
      await page.click("summary:has-text('What Sahaya checked')");
      await axe(page, scheme);
      await page.context().close();
    });
  }

  console.log("\nPhones and odd input");
  for (const [w, h] of [[375, 667], [320, 640]]) {
    await check(`no sideways scrolling on a ${w}px phone, buttons stay tappable`, async () => {
      const page = await freshPage(browser, { viewport: { width: w, height: h }, isMobile: true, hasTouch: true });
      await page.goto(WEB); await page.waitForSelector(".rules");
      await type(page, "anything useful");
      await page.click("text=Choose option 1");
      await page.waitForSelector(".panel");
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over <= 0, `page is ${over}px too wide`);
      const small = await page.$$eval("button, a.btn", (els) => els.filter((e) => {
        const r = e.getBoundingClientRect(); return r.width && (r.height < 44 || r.width < 44);
      }).map((e) => e.textContent.trim()));
      expect(small.length === 0, `too small to tap: ${small.join(", ")}`);
      await page.context().close();
    });
  }

  await check("emoji, other languages and a 2000 character message don't break anything", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await type(page, "Ich brauche eine Uhr ⏰ für Oma");
    await type(page, "a".repeat(2500));          // box stops at 2000
    expect(!page.jsErrors, `JS errors: ${page.jsErrors}`);
    expect(!(await lead(page)).includes("went wrong"), "should not error");
    await page.context().close();
  });

  await check("empty or spaces only can't be sent", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    await page.fill("#say", "    ");
    expect(await page.isDisabled("button[type=submit]"), "send should be disabled");
    await page.context().close();
  });

  console.log("\nWhen things go wrong");
  await check("server stops mid conversation: clear message, no crash", async () => {
    const page = await freshPage(browser);
    await page.goto(WEB); await page.waitForSelector(".rules");
    stopBackend(); await sleep(800);
    await type(page, "a kettle");
    expect((await lead(page)).includes("can't reach my server"), `got: ${await lead(page)}`);
    startBackend(); await waitFor(`${API}/api/health`);
    await page.context().close();
  });

  await check("done page copy for cancelled and failed payments", async () => {
    const page = await freshPage(browser);
    await page.goto(`${WEB}/done?pid=x&result=cancelled`);
    expect((await page.textContent("h1")).includes("cancelled"), "cancelled heading");
    await page.goto(`${WEB}/done?pid=x&result=error`);
    expect((await lead(page)).includes("Nothing was taken"), "error copy");
    await page.context().close();
  });
} finally {
  await browser.close();
  stopBackend();
  preview.kill();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`);
process.exit(failed.length ? 1 : 0);
