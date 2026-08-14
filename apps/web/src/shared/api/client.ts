const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the status-based error when the response is not JSON.
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export function query(path: string, params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const suffix = search.toString();
  return suffix ? `${path}?${suffix}` : path;
}
