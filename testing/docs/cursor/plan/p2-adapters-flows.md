# P2 - Adapters, factories, flows for the rest (strong model for design)
Attach: arch-adapters-factories.md, SUT_MAP.md.
Add concrete HttpAuthApi (no Protocol), KafkaEventReader (concrete, real Redpanda/Kafka), Envelope/payload models for task_created, task_updated, webhook_inbound, webhook_dlq, JWT factory (valid/expired/tampered/alg-none), UserRowFactory (cached argon2 hash), auth flow, WebhookDelivery flow skeleton.
DoD: unit self-tests for factories/models green; pyright clean.
