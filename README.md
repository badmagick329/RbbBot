# RBB Bot

## Existing databases and deployment

Production remains a manual Dokploy deployment. `deployment/build_prod.ps1`
builds committed code, uploads and loads the image, and prints `RBB_IMAGE_TAG`.
Set that tag in Dokploy and redeploy using `notes/dokploy/docker-compose.yaml`.
Preparing the image does not run migrations or restart production.

Container and development startup both run `python -m rbb_bot.upgrade_database`
before launching the bot. It validates Aerich history, verifies the encryption
key, applies pending migrations, then verifies/converts encrypted data. Failure
stops startup. The bot itself never creates or repairs tables.

For an existing database, retain its volume and `RBB_DATA_ENCRYPTION_KEY`.
Check `SELECT version FROM aerich WHERE app = 'models' ORDER BY id;` against
`migrations/models/` before deployment. History must be an uninterrupted prefix
of this release's migration files. Missing history, gaps, or newer unknown
versions stop startup rather than guessing the database state.

This lifecycle release adds no migration for existing databases. If older
migrations are pending, take a database backup and verify its restore procedure
with the original encryption key first. Image rollback does not reverse database
changes. Migration 53 is irreversible and requires encryption conversion to have
completed in the earlier encryption release; do not skip that staged upgrade.

`AERICH_BOOTSTRAP=1` is only the historical one-time path for the specifically
validated legacy schema and empty Aerich table. It records migrations 43-48.
It is not fresh-database initialization or a repair command. Do not enable it
on current production, and remove it after any authorized legacy baseline.

## Fresh database initialization

Create a dedicated empty Postgres database and supply `DB_URL` and
`RBB_DATA_ENCRYPTION_KEY`. For local development, put them in `.env` and run:

```powershell
poetry run python -m rbb_bot.initialize_database --env-file .env
poetry run python -m rbb_bot.dev_start
```

For a new container deployment, run `python -m rbb_bot.initialize_database` once
in the prepared image with those environment variables, before starting the bot.
Use the same database network and environment as the bot. Do not run this command
against the existing production database.

Initialization refuses any existing relation in the public schema. It installs
the frozen schema through migration 53, records the corresponding Aerich history,
and creates encryption metadata in one transaction. A failure rolls everything
back. Normal startup subsequently applies any newer migrations.

The frozen SQL and model snapshot in `rbb_bot/infrastructure/database/` are baseline
assets, not generated on startup. Future schema changes belong in numbered
`migrations/models/` files. Keep the baseline unchanged and test both fresh
initialization followed by upgrades and upgrades containing existing data.

## Development and shutdown

Use `poetry run python -m rbb_bot.dev_start`. It loads the ignored `.env`, keeping
already-set environment variables, then runs the shared upgrade path and launcher.
Avoid launching the bot directly, which bypasses upgrades. The explicit initializer
loads a file only when `--env-file` is provided; production reads process variables.

Docker SIGTERM and console interrupts now trigger awaited shutdown. Logging,
scheduled scraping, guild cleanup, emoji posts, and reminder delivery stop before
their dependent clients close. The launcher owns the shared HTTP session and local
log handler; the bot owns its database connections and Discord logging task.
Discord logging failures are reported locally and do not block the scraper forever.

## Reminders refactor deployment

This release keeps the existing `reminder` table, foreign keys, timestamps, and
`text_ciphertext` encryption format. It needs no new schema or data migration.
Existing pending reminders are picked up after Discord becomes ready.

Prepare the committed release with `deployment/build_prod.ps1`, then set its
printed `RBB_IMAGE_TAG` in Dokploy and redeploy manually. Production uses
`notes/dokploy/docker-compose.yaml`. Run one bot instance; stop the previous
instance before starting the replacement to avoid competing reminder deliveries.
Keep the existing database volume and `RBB_DATA_ENCRYPTION_KEY`.

Normal container startup still runs the encryption preflight, Aerich upgrades,
and encryption conversion before launching the bot. Before deployment, check the
actual Aerich history for the target database against the previous release;
this refactor does not make an older, unconverted database ready for migration 53.
Do not enable `AERICH_BOOTSTRAP` on an already-baselined database. Fresh databases
use the explicit initialization command above.

The worker checks due reminders every 30 seconds and retries failed deliveries
on subsequent polls. Unavailable or forbidden channels fall back to DMs;
failed DMs leave the reminder pending. A failed reminder does not stop others.
Cancellation removes pending database work; a send already in progress cannot
be recalled. A crash after sending but before deletion can cause a duplicate.

After deployment, verify an existing pending reminder, a new DM reminder,
channel delivery, and cancellation. Rolling back this refactor requires only
the prior compatible image, provided startup applied no other pending database
migrations. Image rollback never reverses those migrations. For any pending
schema changes, verify a database backup and restore procedure with the existing
encryption key before deploying.

## Tags refactor deployment

This release changes no tag or response columns, relationships, encryption, or
lookup tokens. Existing databases need no new migration for the tag refactor;
use the normal prepared-image and Dokploy deployment flow above.

Exact tags still take precedence over inline tags. Inline triggers match literal
text at word boundaries, with tag ID order breaking ties. Opted-out users are
skipped before message content is read, and command messages are excluded.
Usage counts retain the existing behavior of counting selected responses before
Discord delivery, so a failed send may still count as a use.

Tag edits, response removal, emoji-channel changes, and guild cleanup invalidate
cached configuration. The next matching request reloads it; ordinary matching
uses the cache. Listing tags reads current usage counts without deleting empty
tags. Removing a tag now preserves responses still shared with other tags.

After deployment, check exact and inline responses, a trigger edit, response
removal, opt-out, and emoji-channel exclusion. Run one bot process as before;
the configuration cache is local to that process. Image rollback needs no data
conversion for this refactor, subject to any other pending migrations applied
at startup.
