import type { JobeApi } from "./client";
import { httpApi } from "./http";
import { mockApi } from "./mock";

function useMock(): boolean {
  const flag = window.__JOBE_USE_MOCK__ ?? import.meta.env.VITE_USE_MOCK ?? "true";
  return flag !== "false";
}

export const api: JobeApi = new Proxy({} as JobeApi, {
  get(_t, prop) {
    const impl = useMock() ? mockApi : httpApi;
    const value = impl[prop as keyof JobeApi];
    return typeof value === "function" ? value.bind(impl) : value;
  },
});

export { useMock };
export type { JobeApi } from "./client";
export * from "./types";
export * from "./labels";
