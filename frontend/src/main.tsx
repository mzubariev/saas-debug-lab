import React from "react"
import ReactDOM from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import * as Sentry from "@sentry/react"
import App from "./App"
import "./index.css"

// Initialise Sentry before the React tree mounts so that every component
// render, navigation, and fetch() is covered from the very first frame.
// BrowserTracing automatically adds `sentry-trace` and `baggage` headers to
// all outgoing fetch() calls whose URL matches tracePropagationTargets, which
// lets the backend SDKs link their spans into the same distributed trace.
Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN || "",
  enabled: !!import.meta.env.VITE_SENTRY_DSN,
  integrations: [
    Sentry.browserTracingIntegration(),
  ],
  // Propagate trace context to every request that targets localhost (the Nginx
  // reverse-proxy) so the full Browser → Gateway → Service chain is linked.
  tracePropagationTargets: [/localhost/],
  // 100 % sampling is fine for a local lab; lower this in real environments.
  tracesSampleRate: parseFloat(
    import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? "1.0"
  ),
  environment: import.meta.env.MODE,
})

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {/* Sentry.ErrorBoundary catches React render errors and reports them to
        Sentry with full component stack, preserving the active trace. */}
    <Sentry.ErrorBoundary
      fallback={
        <div style={{ padding: "2rem", fontFamily: "monospace" }}>
          <h2>Something went wrong.</h2>
          <p>The error has been reported automatically.</p>
        </div>
      }
      showDialog
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Sentry.ErrorBoundary>
  </React.StrictMode>
)
