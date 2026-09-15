/**
 * Captures the screenshots used in the README.
 *
 *   npm run build && npm run preview      # in one terminal (needs the API running)
 *   node scripts/screenshots.mjs          # in another
 *
 * Set BASE_URL to point somewhere else (default http://127.0.0.1:4173).
 */

import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL ?? "http://127.0.0.1:4173";
const OUT_DIR = process.env.OUT_DIR ?? "../docs/screenshots";
const VIEWPORT = { width: 1440, height: 900 };

const SHOTS = [
  { name: "dashboard", path: "/", wait: "Dashboard" },
  { name: "chamados", path: "/chamados", wait: "Chamados" },
  { name: "chamado-detalhe", path: null, wait: "Análise da IA" },
  { name: "base-de-conhecimento", path: "/base-de-conhecimento", wait: "Base de conhecimento" },
  { name: "administracao", path: "/administracao", wait: "Administração" },
];

async function login(page, email) {
  await page.goto(`${BASE_URL}/`);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill("resolveai123");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForSelector("nav");
}

async function capture(page, name, theme) {
  if (name === "dashboard") {
    // Charts only draw once their data arrived and the container has a size.
    await page.locator(".recharts-bar-rectangle").first().waitFor({ timeout: 15000 });
  }
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT_DIR}/${name}${theme === "dark" ? "-escuro" : ""}.png` });
  console.log(`saved ${name}${theme === "dark" ? "-escuro" : ""}.png`);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: VIEWPORT, locale: "pt-BR" });
await mkdir(OUT_DIR, { recursive: true });

await login(page, "admin@resolveai.dev");

for (const theme of ["light", "dark"]) {
  if (theme === "dark") {
    await page.getByRole("button", { name: "Tema escuro" }).click();
    await page.waitForTimeout(200);
  }
  for (const shot of SHOTS) {
    if (shot.path) {
      await page.goto(`${BASE_URL}${shot.path}`);
    } else {
      // Open the first ticket that has an AI analysis, so the screen shows every panel.
      await page.goto(`${BASE_URL}/chamados`);
      const rows = page.locator("tbody tr a");
      for (let index = 0; index < 6; index += 1) {
        await rows.nth(index).click();
        await page.waitForTimeout(600);
        if (await page.getByText("Análise da IA").first().isVisible()) break;
        await page.goBack();
        await page.waitForTimeout(400);
      }
    }
    await page.getByText(shot.wait, { exact: false }).first().waitFor({ timeout: 15000 });
    await capture(page, shot.name, theme);
  }
}

await browser.close();
