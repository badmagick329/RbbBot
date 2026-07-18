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
