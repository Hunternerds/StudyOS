# Migrations

Schema changes live in `app/db.py` as an ordered list (`MIGRATIONS`). The database's `PRAGMA user_version`
records how many have run; on every start the app applies the missing ones, after writing a
`*.backup-<timestamp>` copy of an existing database. To add a change, append a new function to the list
(never edit an old one).

Run manually: `python -m flask --app run init-db`
