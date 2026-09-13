# Repository validator fixtures

`host/` is a minimal generic repository used to prove `runtime/repo_validator.py` without any Project Orath identity, Notion dependency, browser-runtime assumption, or product-specific branch names.

Tests copy this fixture before mutation so failure cases never alter the accepted baseline.
