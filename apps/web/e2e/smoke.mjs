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
const baseUrl = (process.env.BASE_URL ?? "http://127.0.0.1:5173").replace(/\/$/, "");

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
    console.log(`Checking ${suffix}:${route}`);
    await page.goto(`${baseUrl}/#${route}`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1", { state: "visible" });
    await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 30_000 });
    const audit = await page.evaluate(() => ({
      title: document.querySelector("h1")?.textContent?.trim() ?? "",
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bodyLength: document.body.innerText.length,
    }));
    if (!audit.title) errors.push(`${suffix}:${route}:missing-title`);
    if (audit.overflow > 2) errors.push(`${suffix}:${route}:horizontal-overflow:${audit.overflow}`);
    if (audit.bodyLength < 120) errors.push(`${suffix}:${route}:sparse-render:${audit.bodyLength}`);
    const routeSortHeaders = page.locator("th[aria-sort]");
    if (await routeSortHeaders.count() > 0) {
      const routeHeader = routeSortHeaders.first();
      const routeButton = routeHeader.locator("button.sortable-header");
      await routeButton.click();
      if (await routeHeader.getAttribute("aria-sort") !== "ascending") errors.push(`${suffix}:${route}:ascending-sort-state`);
      await routeButton.click();
      if (await routeHeader.getAttribute("aria-sort") !== "descending") errors.push(`${suffix}:${route}:descending-sort-state`);
    }
  }
  await page.goto(`${baseUrl}/#trades`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 30_000 });
  const sortButtons = page.locator("button.sortable-header");
  if (await sortButtons.count() !== 8) errors.push(`${suffix}:trades:sortable-header-count`);
  const firstSort = sortButtons.first();
  if (await firstSort.getAttribute("aria-sort") !== null) {
    errors.push(`${suffix}:trades:aria-sort-on-button`);
  }
  const firstHeader = page.locator("th[aria-sort]").first();
  if (await firstHeader.getAttribute("aria-sort") !== "none") errors.push(`${suffix}:trades:initial-sort-state`);
  await firstSort.click();
  if (await firstHeader.getAttribute("aria-sort") !== "ascending") errors.push(`${suffix}:trades:ascending-sort-state`);
  await firstSort.click();
  if (await firstHeader.getAttribute("aria-sort") !== "descending") errors.push(`${suffix}:trades:descending-sort-state`);
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-trades.png`), fullPage: true });
  await page.goto(`${baseUrl}/#overview`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 30_000 });
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-overview.png`), fullPage: true });
  await page.goto(`${baseUrl}/#opportunities`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 30_000 });
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-opportunities.png`), fullPage: true });
  await page.goto(`${baseUrl}/#llm-operations`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 30_000 });
  await page.screenshot({ path: path.join(os.tmpdir(), `trading-console-${suffix}-llm-operations.png`), fullPage: true });
  await page.goto(`${baseUrl}/#alerts`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector(".spin"), null, { timeout: 30_000 });
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
