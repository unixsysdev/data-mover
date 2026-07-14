# Security policy

## Supported versions

Security fixes are applied to the latest released minor version.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature. Do not open a public
issue containing credentials, connection strings, database contents, or exploit
details.

## Operational guidance

`data-mover` executes queries with the privileges of the supplied database
account. It is not a SQL sandbox or an authorization boundary.

- Use a dedicated read-only database role.
- Prefer `--url-env` over a DSN on the command line.
- Use TLS and the database driver's certificate-verification options.
- Keep exports outside source repositories and protect them at rest.
- Treat query files and output files as potentially sensitive.
- Never expose the CLI as an unauthenticated network service.
