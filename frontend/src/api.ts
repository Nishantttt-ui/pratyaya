/**
 * API client.
 *
 * The bearer token is held in module scope rather than localStorage. It is
 * short-lived and re-obtained on reload, which keeps it out of persistent
 * browser storage where an XSS payload could read it.
 */
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

let token: string | null = null;
let role: string | null = null;

export function currentRole(): string | null {
  return role;
}

export function isAuthenticated(): boolean {
  return token !== null;
}

export function signOut(): void {
  token = null;
  role = null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");

  const response = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: any) => d.msg).join("; ");
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function signIn(username: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username, password });
  const response = await fetch(`${BASE}/api/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new Error("Incorrect username or password");
  const data = await response.json();
  token = data.access_token;
  role = data.role;
  return data.role;
}

export function fetchSample(limit = 8, newToCreditOnly = false) {
  const query = new URLSearchParams({
    limit: String(limit),
    new_to_credit_only: String(newToCreditOnly),
  });
  return request<Record<string, any>[]>(`/api/v1/applicants/sample?${query}`);
}

export function assess(applicant: Record<string, any>) {
  const { emi_to_income, ...payload } = applicant;
  return request<import("./types").Assessment>("/api/v1/assessments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchHealth() {
  return request<{ status: string; components: Record<string, unknown> }>("/health");
}
