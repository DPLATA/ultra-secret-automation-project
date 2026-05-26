# Database migrations (Alembic)

Schema for the `statcast` Cloud SQL Postgres instance (provisioned in
`../terraform/`). All migrations are explicit raw SQL via `op.execute`.

## Running migrations

Migrations connect via the Cloud SQL Auth Proxy on e2-micro (listening on
`127.0.0.1:5432`). Credentials come from `../secrets/cloudsql.env`.

```bash
cd db
set -a; source ../secrets/cloudsql.env; set +a
alembic upgrade head        # apply all pending migrations
alembic current             # show current revision
alembic history             # show migration history
alembic downgrade -1        # roll back one revision
```

## Creating a new migration

```bash
cd db
alembic revision -m "describe the change"
# edit alembic/versions/<rev>_<slug>.py — fill in upgrade() / downgrade()
```

Then commit + apply on e2.
