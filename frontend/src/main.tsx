import { initTelemetry } from "./telemetry"
import React from "react"
import ReactDOM from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import * as Sentry from "@sentry/react"
import App from "./App"
import "./index.css"

// OpenTelemetry must register fetch/XHR instrumentation before React render.
initTelemetry()

// Initialise Sentry before the React tree mounts so that every component
// render, navigation, and fetch() is covered from the very first frame.
Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN || "",
  enabled: !!import.meta.env.VITE_SENTRY_DSN,
  integrations: [
    Sentry.browserTracingIntegration(),
  ],
  tracePropagationTargets: [/localhost/],
  tracesSampleRate: parseFloat(
    import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? "1.0"
  ),
  environment: import.meta.env.MODE,
})

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
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
