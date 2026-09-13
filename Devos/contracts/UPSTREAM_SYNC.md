# Upstream Sync Contract

Live upstream reads/writes are bounded exceptions, not prerequisites for ordinary repo work. Trigger them only when an authority-sensitive decision materially depends on upstream state not represented locally, or when a verified durable delta must be persisted upstream.

Never browse upstream memory freely to rediscover facts already present in the local bundle. Never claim upstream state changed unless the write succeeded and was verified.
