let csrfToken = null;

async function parse(response) {
  const payload = await response.json().catch(() => ({ detail: response.statusText }));
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

export async function bootstrap() {
  const payload = await parse(await fetch("/api/health", { credentials: "same-origin" }));
  csrfToken = payload.csrf_token;
  return payload;
}

export async function apiGet(path) {
  if (!csrfToken) await bootstrap();
  return parse(await fetch(path, { credentials: "same-origin" }));
}

export async function apiGetText(path) {
  if (!csrfToken) await bootstrap();
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

export async function apiPost(path, body) {
  if (!csrfToken) await bootstrap();
  return parse(await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Alysia-CSRF": csrfToken },
    body: JSON.stringify(body),
  }));
}

export function safeArtifactUrl(url) {
  if (typeof url !== "string" || !url.startsWith("/api/runs/") || !url.includes("/artifacts/")) return null;
  if (url.includes("..") || url.includes("\\") || /^https?:/i.test(url)) return null;
  return url;
}
