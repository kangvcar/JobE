/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE: string;
  readonly VITE_USE_MOCK: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  __JOBE_API_BASE__?: string;
  __JOBE_USE_MOCK__?: string;
}

declare module "cytoscape-fcose" {
  const ext: unknown;
  export default ext;
}
