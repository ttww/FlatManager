const TOKEN_KEY = "flatmanager.adminToken";

export function getAdminToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setAdminToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAdminToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}
