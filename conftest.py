"""Repo-root conftest: its presence puts the repo root on sys.path, so tests can `import seam`
and `import analysis` (the project is not an installed package: `[tool.uv] package = false`)."""
