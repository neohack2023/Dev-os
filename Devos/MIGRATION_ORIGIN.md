# Migration origin

Portable DevOS was extracted from the implementation proven inside `neohack2023/project-orath`.

Source repository tree: `340e69d2156229188208cb4c5c181da7525175e9`

Source `devos/` tree: `5be8163a880fb77b2b4984d8b36472c3c5134fbf`

The Orath implementation demonstrated STONE/MASON governance, knowledge branches, autonomous research, task queues, reflection, executable-learning thresholds, tool registry, runtime DB concepts, CI signaling, and upstream synchronization.

This distribution intentionally does **not** ship Orath's project identity, populated task/event/opportunity ledgers, research receipts, Google-sync receipts, Daggerfall-specific knowledge, or host-specific runtime DB artifacts.

Stage 1 neutralizes the package boundary and provides a portable stdlib-only bootstrap/validation runtime. Later extraction slices may migrate richer Orath runtime components only after removing host-specific assumptions and adding portable tests.
