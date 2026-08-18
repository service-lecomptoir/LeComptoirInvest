/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the fund's API lives. Empty in development: the dev server proxies /api. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
