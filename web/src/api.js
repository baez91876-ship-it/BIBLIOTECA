import { reactive } from "vue";

const baseUrl = (window.BIBLIOTECA_API_URL || "").replace(/\/+$/, "");

export const session = reactive({ accessToken: null, refreshToken: null, user: null });

export const isStaff = () =>
  ["bibliotecario", "administrador"].includes(session.user?.rol);

async function parse(response) {
  if (!response.ok) {
    let detail = `Error ${response.status}: no se pudo completar la operación.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((i) => i.msg).join(" ");
    } catch {
      // Cuerpo sin JSON: se conserva el mensaje genérico.
    }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

async function send(url, options) {
  try {
    return await fetch(url, options);
  } catch {
    throw new Error("No se pudo conectar con la API de biblioteca.");
  }
}

let refreshing = null;

async function renew() {
  if (!session.refreshToken) return false;
  refreshing ??= (async () => {
    const response = await send(`${baseUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    if (!response.ok) return false;
    const tokens = await response.json();
    session.accessToken = tokens.access_token;
    session.refreshToken = tokens.refresh_token;
    return true;
  })();
  try {
    return await refreshing;
  } finally {
    refreshing = null;
  }
}

export function clearSession() {
  session.accessToken = null;
  session.refreshToken = null;
  session.user = null;
}

export async function api(path, options = {}) {
  const { retrying = false, ...rest } = options;
  const isForm = rest.body instanceof FormData;
  const response = await send(`${baseUrl}/api/v1${path}`, {
    ...rest,
    headers: {
      ...(rest.body && !isForm ? { "Content-Type": "application/json" } : {}),
      ...(session.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : {}),
      ...rest.headers,
    },
  });
  if (response.status === 401 && session.accessToken) {
    if (!retrying && (await renew())) return api(path, { ...options, retrying: true });
    clearSession();
  }
  return parse(response);
}

export async function login(email, password) {
  const response = await send(`${baseUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  const tokens = await parse(response);
  session.accessToken = tokens.access_token;
  session.refreshToken = tokens.refresh_token;
  try {
    session.user = await api("/auth/me");
  } catch (error) {
    clearSession();
    throw error;
  }
}

export async function logout() {
  const token = session.refreshToken;
  clearSession();
  if (!token) return;
  await send(`${baseUrl}/api/v1/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: token }),
  }).catch(() => {});
}

export async function listAll(path) {
  const records = [];
  for (let skip = 0; ; skip += 100) {
    const page = await api(`${path}?skip=${skip}&limit=100`);
    const items = Array.isArray(page) ? page : page.items;
    records.push(...items);
    if (items.length < 100) return records;
  }
}
