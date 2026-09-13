# MASON Assembly Contract

MASON consumes a locked STONE package when durable knowledge may change. It decides what surviving material becomes, where it belongs, whether it is strong enough to promote, how it is written, and how the write is verified.

Preserve authority labels separately from freshness, usefulness, confidence, and prevalence.

Repository-accepted operating knowledge may be promoted through normal reviewed repository changes plus tests/CI. External project memory remains governed by the host's configured authority. A repo agent may prepare a bounded sync delta but must not claim an upstream write occurred unless it was actually executed and verified.

Every durable mutation plan names the source STONE manifest, exact target, exact delta, authority effect, preconditions, destination authority, rollback/failure behavior, verification method, and required authorization.

A no-op durable result is valid. One execution attempt should produce one immutable receipt after writes stop and independent verification completes.
