# Contributing

Contributions are welcome. Please open an issue before large behavioral changes.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,arrow]'
pre-commit install
```

Run the complete local quality gate:

```bash
ruff check .
ruff format --check .
mypy src
pytest
python -m build
python -m twine check dist/*
```

## Pull requests

- Add tests for observable behavior.
- Preserve backwards compatibility unless the change is explicitly documented.
- Do not commit database credentials, exports, customer data, or production DSNs.
- Update `CHANGELOG.md` for user-visible changes.
- Keep commits focused and use clear, imperative messages.
