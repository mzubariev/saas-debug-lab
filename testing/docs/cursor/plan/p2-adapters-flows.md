# P2: Adapters, factories and flows for the remaining services
Use a strong model for the design part.

Attach: `design/arch-adapters-factories.md`, `SUT_MAP.md`, `sut/auth-service.md` and `sut/webhook-dispatcher.md`.

Must do: add the concrete `HttpAuthApi` (no Protocol) and the concrete `KafkaEventReader` (real Redpanda or Kafka). Add the Envelope and payload models for `task_created`, `task_updated`, `webhook_inbound` and `webhook_dlq`. Add a JWT factory (valid, expired, tampered, `alg=none`), `UserRowFactory` (with one cached argon2 hash), the auth flow and a `WebhookDelivery` flow skeleton. Update `KIT_MAP.md` with everything you added.

Definition of done: the unit self-tests for factories and models are green, pyright is clean, and `KIT_MAP.md` is updated.
