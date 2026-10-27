# Deployment and rollback

## Release checks

1. Work only from a clean commit.
2. Run `python -m ruff check .`, `python -m mypy src`, and `python -m pytest`.
3. Push the commit and wait for GitHub Actions.
4. Create a versioned checkpoint tag after CI passes.
5. Back up the SQLite state and config before deployment.

## Deploying with positions open

1. Announce the deployment.
2. Pause new entries and cancel pending entry orders; leave protective stops in place.
3. Back up the database.
4. Deploy the new image or checkout.
5. Start in paper/shadow mode and reconcile state before resuming.
6. Replay the recent recorded data as a smoke test.
7. Resume only after feeds, clock, database, and reconciliation are healthy.
8. Watch WARN-and-above alerts for 30 minutes.

## Rollback

Keep the previous image tag or Git tag. If reconciliation or smoke tests fail:

1. Stay paused at L1.
2. Restore the previous version.
3. Reconcile again.
4. Keep the bot paused until the incident is understood.

Risk or strategy changes must run in paper/shadow mode before promotion.
