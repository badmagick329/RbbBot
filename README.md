# RBB Bot

## Production migrations

The container runs `aerich upgrade` before starting the bot. A failed migration
prevents the bot from starting.

Production was initially deployed without Aerich history. For the first image
that contains this migration flow only, set `AERICH_BOOTSTRAP=1` in Dokploy.
The bootstrap verifies the known legacy schema, records migrations 43--48
without executing their historical SQL, then applies pending migrations.

After the deployment has successfully started, remove `AERICH_BOOTSTRAP` from
Dokploy and redeploy or restart the service. Leaving it enabled intentionally
prevents later starts, because the baseline may only be created once.

Migration 49 permanently removes `commandlog`; its historical data is not
recoverable.

## Development startup

Run the development entry point instead of invoking `launcher.py` directly:

```powershell
poetry run python -m rbb_bot.dev_start
```

It reads development settings from the ignored root `.env` file,
applies pending Aerich migrations, then starts the normal bot launcher. An
explicit `DB_URL` environment variable takes precedence when needed.

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
Do not enable `AERICH_BOOTSTRAP` on an already-baselined database. Fresh-database
initialization and the existing schema-generation behavior are unchanged here.

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
