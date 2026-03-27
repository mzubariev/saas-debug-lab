/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_SENTRY_DSN?: string
  readonly VITE_SENTRY_TRACES_SAMPLE_RATE?: string
  /** OTLP HTTP traces URL. Defaults in dev to same-origin `/otel/v1/traces` (Vite proxy → Jaeger). */
  readonly VITE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
