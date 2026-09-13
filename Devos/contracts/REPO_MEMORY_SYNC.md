# Repository ↔ Memory Sync Contract

Repository execution facts and external durable memory are distinct authority surfaces. Synchronization moves bounded deltas and pointers, not entire repositories or giant context dumps.

A sync delta states what changed, why it matters durably, source commit/artifact evidence, target memory surface, authority effect, and verification. No-op sync is valid.
