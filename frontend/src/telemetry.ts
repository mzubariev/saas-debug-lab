/**
 * OpenTelemetry Web SDK — W3C trace context on fetch/XHR, OTLP HTTP → Collector (:4318) → Jaeger.
 *
 * Default URL is `http://localhost:4318/v1/traces` (Collector maps host ports; CORS allowed in
 * `observability/otel-collector/otel-collector-config.yaml`). Override with
 * `VITE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`.
 */
import { trace, SpanStatusCode, type Span, type Attributes } from "@opentelemetry/api"
import { registerInstrumentations } from "@opentelemetry/instrumentation"
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http"
import { FetchInstrumentation } from "@opentelemetry/instrumentation-fetch"
import { XMLHttpRequestInstrumentation } from "@opentelemetry/instrumentation-xml-http-request"
import { Resource } from "@opentelemetry/resources"
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base"
import { WebTracerProvider } from "@opentelemetry/sdk-trace-web"

let initialized = false

function resolveOtlpTracesUrl(): string {
  const fromEnv = import.meta.env.VITE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT as
    | string
    | undefined
  if (fromEnv) return fromEnv
  return "http://localhost:4318/v1/traces"
}

/**
 * Call once from `main.tsx` before Sentry and React render so fetch/XHR are
 * instrumented before any API traffic.
 */
export function initTelemetry(): void {
  if (initialized) return
  initialized = true

  const exporter = new OTLPTraceExporter({
    url: resolveOtlpTracesUrl(),
  })

  const provider = new WebTracerProvider({
    spanProcessors: [new BatchSpanProcessor(exporter)],
    resource: new Resource({
      "service.name": "saas-debug-lab-frontend",
    }),
  })

  provider.register()

  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        propagateTraceHeaderCorsUrls: [/.+/],
        clearTimingResources: true,
      }),
      new XMLHttpRequestInstrumentation({
        propagateTraceHeaderCorsUrls: [/.+/],
      }),
    ],
  })
}

const TRACER_NAME = "saas-debug-lab-frontend"

export function getFrontendTracer() {
  return trace.getTracer(TRACER_NAME)
}

/**
 * Wrap async work in a named span (manual instrumentation for user actions).
 * Child HTTP spans nest under this span; W3C headers propagate to the gateway.
 */
export async function runWithSpan<T>(
  name: string,
  fn: (span: Span) => Promise<T>,
  attributes?: Attributes
): Promise<T> {
  const tracer = trace.getTracer(TRACER_NAME)
  return tracer.startActiveSpan(name, async span => {
    if (attributes) {
      span.setAttributes(attributes)
    }
    if (import.meta.env.DEV) {
      const sc = span.spanContext()
      if (sc.traceId) {
        console.debug(`[otel] trace_id=${sc.traceId} span=${name}`)
      }
    }
    try {
      const out = await fn(span)
      span.setStatus({ code: SpanStatusCode.OK })
      return out
    } catch (err) {
      span.setStatus({ code: SpanStatusCode.ERROR })
      span.recordException(err as Error)
      throw err
    } finally {
      span.end()
    }
  })
}
