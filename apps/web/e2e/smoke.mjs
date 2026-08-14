import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { chromium } from "playwright";

const candidates = [
  process.env.BROWSER_PATH,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No Chromium-compatible browser was found");

const routes = ["overview", "performance", "trades", "opportunities", "strategies", "market", "alerts", "llm-operations", "reports", "data-quality"];
const errors = [];
const browser = await chromium.launch({ executablePath, headless: true });

async function verifyViewport(viewport, suffix) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`${suffix}:console:${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`${suffix}:page:${error.message}`));
  for (const route of routes) {
    await page.goto(`http://127.0.0.1:5173/#${route}`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1", { state: "visible" });
    await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 15_000 });
    const audit = await page.evaluate(() => ({
      title: document.querySelector("h1")?.textContent?.trim() ?? "",
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bodyLength: document.body.innerText.length,
    }));
    if (!audit.title) errors.push(`${suffix}:${route}:missing-title`);
    if (audit.overflow > 2) errors.push(`${suffix}:${route}:horizontal-overflow:${audit.overflow}`);
    if (audit.bodyLength < 120) errors.push(`${suffix}:${route}:sparse-render:${audit.bodyLength}`);
  }
  await page.goto("http://127.0.0.1:5173/#overview", { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 15_000 });
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-overview.png`), fullPage: true });
  await page.goto("http://127.0.0.1:5173/#opportunities", { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 15_000 });
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-opportunities.png`), fullPage: true });
  await page.goto("http://127.0.0.1:5173/#llm-operations", { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 15_000 });
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-llm-operations.png`), fullPage: true });
  await page.goto("http://127.0.0.1:5173/#alerts", { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 15_000 });
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-alerts.png`), fullPage: true });
  await context.close();
}

await verifyViewport({ width: 1440, height: 1000 }, "desktop");
await verifyViewport({ width: 390, height: 844 }, "mobile");
await browser.close();

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log(`Verified ${routes.length} routes at desktop and mobile viewports.`);
console.log(path.join(os.tmpdir(), "trading-console-desktop-overview.png"));
console.log(path.join(os.tmpdir(), "trading-console-mobile-overview.png"));
