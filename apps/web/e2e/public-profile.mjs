import fs from "node:fs";

import { chromium } from "playwright";

const candidates = [
  process.env.BROWSER_PATH,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No Chromium-compatible browser was found");

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.route("**/health/ready", async (route) => {
  await route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      status: "AVAILABLE",
      checked_at: new Date().toISOString(),
      read_only: true,
      execution_callable: false,
      exposure_profile: "public",
      public_mode: true,
      sources: [],
    }),
  });
});
await page.goto("http://127.0.0.1:5173/#overview", { waitUntil: "networkidle" });

const text = await page.locator("body").innerText();
const failures = [];
if (!text.includes("PUBLIC SHOWCASE")) failures.push("missing public profile marker");
if (!text.includes("SIMULATION / MOCK")) failures.push("missing simulation marker");
for (const privateLabel of ["LLM 운영", "리포트", "데이터 품질"]) {
  if (await page.locator("nav").getByText(privateLabel, { exact: true }).count()) {
    failures.push(`private navigation visible: ${privateLabel}`);
  }
}
await browser.close();
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("Verified public-profile navigation and mode markers.");
