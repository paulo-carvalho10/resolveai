/**
 * Captures the screenshots used in the README.
 *
 *   docker compose up -d --build          # app on :5173, with the API behind /api
 *   node scripts/screenshots.mjs
 *
 * Needs the seed and the demo data. The app and the API must share an origin (the nginx
 * container or `npm run dev`): `npm run preview` serves the app on another port, and the API
 * rejects it (CORS). Set BASE_URL to point somewhere else (default http://127.0.0.1:5173).
 */

import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL ?? "http://127.0.0.1:5173";
const PASSWORD = "resolveai123";
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
  await page.getByLabel("Senha").fill(PASSWORD);
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

// A requester who solved the problem alone, seen by both sides. The ticket is created only for
// these captures, after the others so it never appears in them, and deleted at the end.
async function api(path, { token, method = "GET", body } = {}) {
  const response = await fetch(`${BASE_URL}/api${path}`, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`${method} ${path}: HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}

const tokenFor = async (email) =>
  (await api("/auth/login", { method: "POST", body: { email, password: PASSWORD } })).access_token;
const [requesterToken, adminToken] = await Promise.all(
  ["user@resolveai.dev", "admin@resolveai.dev"].map(tokenFor),
);
const showcase = await api("/tickets", {
  token: requesterToken,
  method: "POST",
  body: {
    title: "Impressora fiscal não imprime o cupom",
    description: "A impressora do caixa 2 parou de imprimir os cupons fiscais desde a abertura da loja.",
  },
});
try {
  await api(`/tickets/${showcase.id}/self-resolve`, {
    token: requesterToken,
    method: "POST",
    body: {
      solution:
        "Reiniciei o serviço de spooler do Windows no computador do caixa e a impressora voltou a imprimir os cupons.",
    },
  });

  for (const [email, name, waitFor] of [
    ["user@resolveai.dev", "resolvido-pelo-solicitante", "Solução do solicitante"],
    ["agent@resolveai.dev", "revisao-da-equipe", "Análise da IA"],
  ]) {
    const sidePage = await browser.newPage({ viewport: VIEWPORT, locale: "pt-BR" });
    await login(sidePage, email);
    await sidePage.goto(`${BASE_URL}/chamados/${showcase.id}`);
    await sidePage.getByText(waitFor).first().waitFor({ timeout: 15000 });
    await capture(sidePage, name, "light");
    await sidePage.close();
  }
} finally {
  await api(`/tickets/${showcase.id}`, { token: adminToken, method: "DELETE" });
}

await browser.close();
