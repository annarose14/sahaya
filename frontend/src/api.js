const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function call(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export const api = {
  health: () => call("GET", "/api/health"),
  chat: (session_id, message) => call("POST", "/api/chat", { session_id, message }),
  purchase: (pid) => call("GET", `/api/purchases/${pid}`),
  purchases: (sid) => call("GET", `/api/sessions/${sid}/purchases`),
  trace: (sid) => call("GET", `/api/sessions/${sid}/trace`),
  confirm: (pid) => call("POST", `/api/purchases/${pid}/confirm`),
  cancel: (pid) => call("POST", `/api/purchases/${pid}/cancel`),
  refund: (pid) => call("POST", `/api/purchases/${pid}/refund`),
  family: (pid, approve) => call("POST", `/api/purchases/${pid}/family`, { approve }),
};

export function sessionId() {
  let id = null;
  try { id = localStorage.getItem("sahaya_sid"); } catch {}
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)).replace(/-/g, "").slice(0, 20);
    try { localStorage.setItem("sahaya_sid", id); } catch {}
  }
  return id;
}

export function money(n, cur = "USD") {
  try {
    return new Intl.NumberFormat("en-AU", { style: "currency", currency: cur }).format(n);
  } catch {
    return `${Number(n).toFixed(2)} ${cur}`;
  }
}
