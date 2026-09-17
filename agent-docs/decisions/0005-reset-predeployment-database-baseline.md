# 0005 — Reset the pre-deployment database baseline

## Status

Accepted before any supported deployment; supersedes the legacy database adoption and upgrade commitments in decisions 0001, 0002, and 0004.

## Decision

- No existing TaskRelay database is supported as production data yet.
- Replace all historical migrations with one Alembic `0001_initial` migration representing the complete 0.4 schema.
- Remove frozen v0.1 schema detection, legacy adoption, historical bootstrap attribution, and upgrade documentation.
- Development databases and volumes created before this baseline are intentionally discarded.
- Alembic remains the schema authority so every future deployed release can add forward migrations from `0001_initial`.

## Consequence

Starting 0.4 requires a fresh database. This reset must not be repeated after the first supported deployment without an explicit data-migration plan.
