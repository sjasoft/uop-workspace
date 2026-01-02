# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **uop-workspace**, a Python monorepo implementing the **Universal Object Platform (UOP)** - a modular database abstraction layer with metadata management and multi-backend support. The architecture enables database-agnostic application development through adapter/plugin patterns.

**Key Goal**: Allow developers to swap database backends (MongoDB, PostgreSQL, SQLite, Neo4j, SQLAlchemy) without changing application code.

## Essential Commands

### Workspace Setup
```bash
# Install all workspace dependencies
uv sync

# Install dependencies for a specific package
cd packages/<package-name>
uv sync
```

### Testing
```bash
# Run all tests in workspace
pytest

# Run tests for specific package
cd packages/<package-name>
pytest

# Run specific test file
pytest tests/test_file.py

# Run with async support (common in this codebase)
pytest -v --asyncio-mode=auto

# Run with coverage
pytest --cov=src --cov-report=html

# Parallel test execution
pytest -n auto
```

### Package Development
```bash
# Build a package
cd packages/<package-name>
uv build

# Install package in editable mode (workspace handles this automatically)
uv sync
```

## Architecture

### Package Organization

The monorepo contains 15+ packages organized in layered architecture:

**Foundation Layer:**
- `sjasoft-utils`: Core utilities (logging, data manipulation, datetime, decorators, iterators, etc.)
- `sjasoft-web`: Web utilities and URL handling

**Schema/Metadata Layer:**
- `uop-meta`: Schema definitions using Pydantic, query construction (AndQuery, OrQuery), metadata modeling

**Core Business Logic:**
- `uop-core`: Central abstraction layer
  - `db_interface.py`: Main `Interface` class (all external-facing functionality)
  - `database.py`: Database abstraction and connection management
  - `query.py`: Query builder (`Q` class) with MongoDB-style operators ($gt, $lt, $eq, $and, $or, $regex)
  - `changeset.py`: Change tracking before applying to database
  - `connect/`: Connection strategies (direct, async, web, generic)
  - `plugin_testing/`: Test harness (`Plugin`, `AsyncPlugin`) for database adapters

**Database Adapters (uop-db-*):**
- `uop-db-mongo`: MongoDB (motor async, pymongo sync)
- `uop-db-postgres`: PostgreSQL (asyncpg, psycopg2)
- `uop-db-sqlite`: SQLite
- `uop-db-alchemy`: SQLAlchemy 2.0+
- `uop-db-neo4j`: Neo4j graph database

Each adapter implements:
- `adaptor.py`: Synchronous implementation
- `async_adaptor.py`: Asynchronous variant (where applicable)
- Collection wrapper extending `DBCollection`

**SQL Layer (uop-sql-*):**
- `uop-sql-base`: Base SQL abstraction
- `uop-sql-postgres`, `uop-sql-mariadb`, `uop-sql-sqlite`: Dialect-specific implementations

**Client/Application:**
- `uop-client`: Client-side state management
- `uop-app-pyside`: PySide6 desktop GUI

### Dependency Flow
```
sjasoft-utils → uop-meta → uop-core → uop-db-* adapters
                                    ↘ uop-client
                                    ↘ uop-sql-* dialects
```

### Key Architectural Patterns

**1. Adapter Pattern**: Database implementations are pluggable. The same `Interface` class in `uop-core` works with any compliant adapter.

**2. Metadata-Driven**: Heavy use of Pydantic models and `uop-meta` schemas for runtime type discovery and validation.

**3. Query Builder**: Custom `Q` class in `uop-core.query` mimics MongoDB/Django ORM patterns:
```python
Q(field__gt=10) & Q(field__lt=20)  # Chaining with operators
Q(field__regex="pattern")           # Regex support
```

**4. Change Tracking**: `ChangeSet` pattern tracks modifications before database commits.

**5. Multi-Tenancy**: `Interface` supports optional `tenant_id` parameter for data isolation.

**6. Async-First**: Database adapters offer both sync and async variants. Tests use `pytest-asyncio`.

## Development Patterns

### Namespace Packages
All packages use setuptools namespace packages:
```toml
[tool.setuptools.packages.find]
where = ["src"]
namespaces = true
```

This enables shared namespace prefixes (`sjasoft.*`, `uop.*`) without circular dependencies.

### Source Structure
Standard layout across all packages:
```
package-name/
  src/
    uop/              # or sjasoft/
      <module>/
        *.py
  tests/              # At package root, not in src/
  pyproject.toml
```

### Testing Patterns

**Fixture-Based Setup** (example from uop-db-mongo):
```python
@pytest.fixture(scope="session")
def db_harness():
    db = adaptor.MongoUOP(db_name, schema, username="admin", password="password")
    db.open_db()
    plug_in = Plugin(db)
    yield plug_in
    db.drop_and_close()

@pytest_asyncio.fixture(scope="function")
async def async_db_harness():
    db = async_adaptor.MongoUOP(db_name, schema, ...)
    await db.open_db()
    plug_in = AsyncPlugin(db)
    yield plug_in
    await db.drop_and_close()
```

**Plugin Testing Harness**: Use `Plugin` and `AsyncPlugin` classes from `uop-core/plugin_testing/` for standardized database adapter testing.

### Dependencies

**Workspace root** (`pyproject.toml`) specifies shared dev dependencies:
- pytest suite (pytest, pytest-asyncio, pytest-cov, pytest-mock, pytest-timeout, pytest-xdist)
- JupyterLab for notebooks

**Individual packages** specify runtime dependencies in their own `pyproject.toml`:
```toml
[dependency-groups]
dev = ["pytest>=8.4.2", "pytest-asyncio>=1.2.0"]
```

## Key Entry Points for Understanding the Codebase

1. **Start with `uop-core`**: Read `db_interface.py` to understand the main abstraction
2. **Review `uop-meta`**: Check `schemas/meta.py` for schema patterns
3. **Study an adapter**: `uop-db-mongo/src/sjasoft_uopdb_mongo/adaptor.py` shows implementation pattern
4. **Check testing harness**: `uop-core/plugin_testing/` shows how to test new backends

## Important Files

- `uop-core/src/uop/core/db_interface.py`: Main Interface class (4600+ LOC)
- `uop-core/src/uop/core/query.py`: Query builder with MongoDB-style operators
- `uop-core/src/uop/core/changeset.py`: Change tracking system
- `uop-meta/src/uop/meta/schemas/meta.py`: Core schema definitions
- `sjasoft-utils/src/sjasoft/utils/`: 26+ utility modules

## Technology Requirements

- Python >= 3.12
- Package manager: `uv` (workspace-based)
- Build system: setuptools with namespace packages
- Schema validation: Pydantic 1.10.7
- Async runtime: motor, asyncpg, pytest-asyncio
