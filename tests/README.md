# Tests

Run the fast unit suite without Postgres:

```powershell
poetry run pytest
```

Run the full suite against the dedicated local Postgres database:

```powershell
docker compose -f docker-compose-test.yml up -d --wait
poetry run pytest --integration
```

Run only the database integration tests:

```powershell
poetry run pytest --integration -m integration
```

The test database is always `rbb_test` on `127.0.0.1:5433`. It uses its own Docker volume and does not read `.env` or application credentials. Integration tests reset its `public` schema before every test.

Wins client/cache and hybrid-command/embed regressions run without a database or Discord token: `poetry run pytest tests/test_wins.py tests/test_wins_command.py`. Changes to live slash registration, guild permissions or rendering also need Discord smoke checks. The owner confirmed the original rollout checks passed on 2026-10-18; evidence is recorded in [RBB-19](https://badmagick.youtrack.cloud/issue/RBB-19).

`aerich-test.toml` provides the same isolated configuration for Aerich-related test work. Do not use it to deploy migrations; production continues to use the normal deployment configuration.
