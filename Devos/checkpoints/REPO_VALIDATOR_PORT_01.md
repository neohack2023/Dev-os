# REPO_VALIDATOR_PORT_01

Status: **Checkpoint accepted for portable validation gate**

Source implementation: `neohack2023/project-orath/tools/validate_devos.py`
Source blob: `ff70d5e5a12e3113df35f0642b3c855178bec28a`

## Ported behavior

- project identity and authority-shape validation;
- governance-lock consistency;
- local-first / external-memory-optional invariant;
- unique branch registry with dependency validation and cycle detection;
- safe, existing host-surface validation;
- tool registry qualification and pinned revision checks;
- task queue integration;
- package/instance version agreement.

## Removed host assumptions

- fixed `project-orath` scope;
- fixed `neohack2023/project-orath` repository;
- mandatory Orath branch names;
- mandatory Notion URL fields;
- Orath knowledge DB / snapshot / sync receipt paths;
- Project Orath feature-folder conventions.

## Evidence

Portable fixture tests cover:
1. valid generic host;
2. governance/project scope mismatch;
3. missing host surface;
4. branch dependency cycle;
5. unpinned tool revision;
6. forbidden live-external-memory dependency;
7. task route to unknown branch.

The package bootstrap validator delegates initialized-instance validation to this runtime.
