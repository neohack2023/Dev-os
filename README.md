# DevOS

Portable repository-side development intelligence and governance for AI-assisted software projects.

The distributable package lives entirely under [`Devos/`](./Devos). That directory is intentionally self-contained so it can be copied into an existing repository without scattering DevOS-owned files across the host root.

Current portable checkpoint: **v0.3.0**, with neutralized task-queue and repository-validation runtimes.

This repository was extracted from the working DevOS implementation proven in `neohack2023/project-orath`, then neutralized so host-project identity, task history, research receipts, sync history, and other project-specific state do not leak into new installations.

See `Devos/README.md` and `Devos/PORTING.md`.
