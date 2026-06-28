import type {
    AccessCodeForm,
    AccessCodeSummary,
    AccessLogSummary,
    AdminDevice,
    ApartmentTimezone,
    CommandSummary,
    DeviceStatus,
    DeviceUpdatePayload,
    NewDeviceResponse,
    RotateDeviceTokenResponse,
} from "../types";
import { clearAdminToken } from "./session";

function resolveApiBase(): string {
  const configured = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  const origin = window.location.origin;
  const isRemoteHost = !/^localhost$|^127\.0\.0\.1$/.test(window.location.hostname);

  if (!configured) {
    return origin;
  }

  if ((configured.includes("localhost") || configured.includes("127.0.0.1")) && isRemoteHost) {
    return origin;
  }

  return configured;
}

const API_BASE = resolveApiBase();
const BASE_PATH = import.meta.env.VITE_BASE_PATH ?? "/admin/";

function adminLoginPath(): string {
  const base = BASE_PATH.endsWith("/") ? BASE_PATH.slice(0, -1) : BASE_PATH;
  return `${base}/login`;
}

async function request<T>(
  path: string,
  adminToken: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (adminToken) {
    headers.set("X-Admin-Token", adminToken);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearAdminToken();
    if (window.location.pathname !== adminLoginPath()) {
      window.location.replace(adminLoginPath());
    }
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    if (response.status === 413) {
      throw new Error(
        "Upload rejected by reverse proxy (413 Request Entity Too Large). Increase NGINX client_max_body_size or use a smaller image.",
      );
    }
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  listApartmentTimezones(adminToken: string, apartmentId?: string) {
    const query = apartmentId ? `?apartment_id=${encodeURIComponent(apartmentId)}` : "";
    return request<ApartmentTimezone[]>(`/api/admin/apartments${query}`, adminToken);
  },

  createApartment(adminToken: string, payload: { apartment_id: string; timezone: string }) {
    return request<ApartmentTimezone>("/api/admin/apartments", adminToken, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getApartmentTimezone(adminToken: string, apartmentId: string) {
    return request<ApartmentTimezone>(`/api/admin/apartments/${encodeURIComponent(apartmentId)}`, adminToken);
  },

  updateApartmentTimezone(adminToken: string, apartmentId: string, timezone: string) {
    return request<ApartmentTimezone>(
      `/api/admin/apartments/${encodeURIComponent(apartmentId)}/timezone`,
      adminToken,
      {
        method: "PUT",
        body: JSON.stringify({ timezone }),
      },
    );
  },

  deleteApartment(adminToken: string, apartmentId: string) {
    return request<void>(`/api/admin/apartments/${encodeURIComponent(apartmentId)}`, adminToken, {
      method: "DELETE",
    });
  },

  uploadApartmentGuestBackground(adminToken: string, apartmentId: string, file: File) {
    const formData = new FormData();
    formData.append("file", file);
    return request<ApartmentTimezone>(
      `/api/admin/apartments/${encodeURIComponent(apartmentId)}/guest-background`,
      adminToken,
      {
        method: "POST",
        body: formData,
      },
    );
  },

  deleteApartmentGuestBackground(adminToken: string, apartmentId: string) {
    return request<ApartmentTimezone>(
      `/api/admin/apartments/${encodeURIComponent(apartmentId)}/guest-background`,
      adminToken,
      {
        method: "DELETE",
      },
    );
  },

  getDeviceStatus(adminToken: string, apartmentId?: string) {
    const query = apartmentId ? `?apartment_id=${encodeURIComponent(apartmentId)}` : "";
    return request<DeviceStatus[]>(`/api/admin/devices/status${query}`, adminToken);
  },

  getRecentCommands(adminToken: string, apartmentId?: string) {
    const query = apartmentId ? `?apartment_id=${encodeURIComponent(apartmentId)}` : "";
    return request<CommandSummary[]>(`/api/admin/commands/recent${query}`, adminToken);
  },

  getRecentLogs(adminToken: string, apartmentId?: string) {
    const query = apartmentId ? `?apartment_id=${encodeURIComponent(apartmentId)}` : "";
    return request<AccessLogSummary[]>(`/api/admin/access-logs/recent${query}`, adminToken);
  },

  listDevices(adminToken: string) {
    return request<AdminDevice[]>("/api/admin/devices", adminToken);
  },

  createDevice(adminToken: string, payload: { apartment_id: string; device_name: string }) {
    return request<NewDeviceResponse>("/api/admin/devices", adminToken, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  rotateDeviceToken(adminToken: string, deviceId: number) {
    return request<RotateDeviceTokenResponse>(`/api/admin/devices/${deviceId}/rotate-token`, adminToken, {
      method: "POST",
    });
  },

  updateDevice(adminToken: string, deviceId: number, payload: DeviceUpdatePayload) {
    return request<AdminDevice>(`/api/admin/devices/${deviceId}`, adminToken, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  deleteDevice(adminToken: string, deviceId: number) {
    return request<void>(`/api/admin/devices/${deviceId}`, adminToken, {
      method: "DELETE",
    });
  },

  createAccessCode(adminToken: string, payload: AccessCodeForm) {
    return request<AccessCodeSummary>("/api/admin/access-codes", adminToken, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listAccessCodes(adminToken: string, apartmentId?: string) {
    const query = apartmentId ? `?apartment_id=${encodeURIComponent(apartmentId)}` : "";
    return request<AccessCodeSummary[]>(`/api/admin/access-codes${query}`, adminToken);
  },

  updateAccessCode(adminToken: string, codeId: number, payload: Partial<AccessCodeForm>) {
    return request<AccessCodeSummary>(`/api/admin/access-codes/${codeId}`, adminToken, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  deleteAccessCode(adminToken: string, codeId: number) {
    return request<void>(`/api/admin/access-codes/${codeId}`, adminToken, {
      method: "DELETE",
    });
  },

  deactivateAccessCode(adminToken: string, codeId: number) {
    return request<AccessCodeSummary>(`/api/admin/access-codes/${codeId}/deactivate`, adminToken, {
      method: "POST",
    });
  },

  manualOpen(adminToken: string, apartmentId: string) {
    return request<unknown>("/api/admin/commands/manual-open", adminToken, {
      method: "POST",
      body: JSON.stringify({ apartment_id: apartmentId }),
    });
  },

  deleteAllCommands(adminToken: string) {
    return request<void>("/api/admin/commands", adminToken, { method: "DELETE" });
  },

  deleteAllAccessLogs(adminToken: string) {
    return request<void>("/api/admin/access-logs", adminToken, { method: "DELETE" });
  },
};
