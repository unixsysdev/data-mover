# Data Mover

A small Flask prototype for registering SQLAlchemy database connections, running SQL queries, and returning results through pandas.

## Endpoints

- `GET /list` — list configured database definitions
- `POST /connect/<database>` — register connection metadata
- `GET|POST /query/<database>` — execute a query through pandas and SQLAlchemy

Database definitions are expected under `conf.d/` as JSON containing an SQLAlchemy dialect, username, password, hostname, and database name. Do not commit real credentials.

## Running the prototype

The current source uses Python 2 syntax and legacy Flask/pandas APIs. A compatible environment requires Flask, pandas, PyYAML, SQLAlchemy, and a database driver:

```bash
python app.py
```

The development server binds to `0.0.0.0`.

## Status

Early prototype retained for reference. Before use:

- port it to Python 3 and fix connection-field handling
- move secrets to a secret manager or protected environment
- add authentication, authorization, and query restrictions
- replace direct file writes with validated configuration storage
- add input validation, tests, structured errors, and a production WSGI server

Do not expose the current application to an untrusted network.
