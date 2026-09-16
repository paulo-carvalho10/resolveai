import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:5173";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "pt-BR" });
const errors = [];
page.on("pageerror", (error) => errors.push(String(error).slice(0, 200)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text().slice(0, 200)));

async function login(email) {
  await page.goto(`${BASE}/`);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill("resolveai123");
  await page.getByRole("button", { name: "Entrar" }).click();
  // Hosted on a free tier, login (Argon2) can take a few seconds.
  await page.waitForSelector("nav", { timeout: 60000 });
}

// Requester opens a ticket through the UI.
await login("user@resolveai.dev");
await page.getByRole("navigation").getByRole("link", { name: "Novo chamado" }).click();
await page.getByLabel("Título").fill("Não consigo emitir NF-e, rejeição 539");
await page
  .getByLabel("Descrição")
  .fill("A SEFAZ devolve duplicidade da nota e o sistema não transmite. Precisamos faturar hoje.");
await page.getByRole("button", { name: "Abrir chamado" }).click();
await page.waitForURL(/\/chamados\/\d+$/);
const ticketUrl = page.url();
console.log("chamado criado:", ticketUrl);
console.log("prioridade/badges:", (await page.locator("section").first().innerText()).split("\n").slice(0, 4));

// The requester must not see staff-only panels.
console.log("vê triagem?", await page.getByText("Triagem").isVisible().catch(() => false));
console.log("vê histórico?", await page.getByText("Histórico").isVisible().catch(() => false));

// Agent sees the AI analysis and the knowledge base suggestion on the same ticket.
await page.getByRole("button", { name: "Sair" }).click();
await login("agent@resolveai.dev");
await page.goto(ticketUrl);
// Wait for the ticket itself before asking which panels are on screen.
await page.getByRole("heading", { level: 1 }).waitFor({ timeout: 60000 });
await page.getByText("Detalhes").first().waitFor({ timeout: 60000 });
for (const label of ["Análise da IA", "Sugestão da base de conhecimento", "Triagem", "Histórico"]) {
  const visible = await page
    .getByText(label)
    .first()
    .waitFor({ timeout: 30000 })
    .then(() => true)
    .catch(() => false);
  console.log(`agente vê "${label}":`, visible);
}
console.log("sugestão:", (await page.locator("text=Fontes utilizadas").count()) > 0 ? "com fontes" : "sem fontes");
console.log("erros de console:", errors.length ? errors : "nenhum");
await browser.close();
