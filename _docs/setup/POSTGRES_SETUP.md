# PostgreSQL + pgvector Setup

Gabriel stores **all** of its state in a single self-hosted **PostgreSQL**
database with the **[pgvector](https://github.com/pgvector/pgvector)** extension:

| Data                                   | Table(s)                          |
| -------------------------------------- | --------------------------------- |
| Chat sessions                          | `sessions`                        |
| Chat history (messages)                | `messages`                        |
| Agents                                 | `agents`                          |
| Per-agent tool enable/disable state    | `agent_tools`                     |
| Crawler link queue                     | `links`                           |
| Vector knowledge base (embeddings)     | `documents` (pgvector `vector`)   |
| LangGraph conversation checkpoints     | `checkpoints*` (managed by LangGraph) |

> Ollama is still used as an external **embedding/LLM** service. It is **not** a
> storage backend — the embeddings it produces are persisted in PostgreSQL via
> pgvector.

---

## 1. Install PostgreSQL and pgvector

You need **PostgreSQL 13+** and the matching **pgvector** package.

### Debian / Ubuntu

```bash
# Install the PostgreSQL server (replace 17 with your major version if needed)
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib

# Install pgvector for your PostgreSQL major version
# (e.g. postgresql-17-pgvector for PG 17, postgresql-16-pgvector for PG 16, ...)
sudo apt-get install -y postgresql-17-pgvector

# Make sure the server is running
sudo service postgresql start          # or: sudo pg_ctlcluster 17 main start
```

### macOS (Homebrew)

```bash
brew install postgresql@17
brew services start postgresql@17

# pgvector
brew install pgvector
```

### Docker (quickest cross-platform option)

The official `pgvector` image already bundles the extension:

```bash
docker run -d --name gabriel-postgres \
  -e POSTGRES_USER=gabriel \
  -e POSTGRES_PASSWORD=gabriel \
  -e POSTGRES_DB=gabriel \
  -p 5432:5432 \
  pgvector/pgvector:pg17
```

If you use Docker you can skip step 2 (the role and database are created from the
environment variables above) and go straight to step 3.

### Building pgvector from source (if no package is available)

```bash
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

---

## 2. Create the database and role

Create a dedicated role and database. The defaults below match the
`DATABASE_URL` in `.env.example`.

```bash
# Run as the postgres superuser
sudo -u postgres psql <<'SQL'
CREATE ROLE gabriel WITH LOGIN PASSWORD 'gabriel';
CREATE DATABASE gabriel OWNER gabriel;
GRANT ALL PRIVILEGES ON DATABASE gabriel TO gabriel;
SQL
```

> **Note:** The `vector` extension is enabled automatically by the migration
> runner (`python -m db.migrate` issues `CREATE EXTENSION IF NOT EXISTS vector`).
> Enabling an extension requires privileges on the database — the commands above
> make `gabriel` the database owner, which is sufficient. If you prefer to enable
> it manually as the superuser, run:
>
> ```bash
> sudo -u postgres psql -d gabriel -c 'CREATE EXTENSION IF NOT EXISTS vector;'
> ```

---

## 3. Configure environment variables

Copy the example file and adjust it for your environment:

```bash
cp .env.example .env
```

| Variable          | Required | Default                                              | Description                                                                                          |
| ----------------- | :------: | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`    |   yes    | `postgresql://gabriel:gabriel@localhost:5432/gabriel`| PostgreSQL connection string used by the whole app (pool, migrations, repositories, checkpointer).   |
| `EMBEDDING_DIM`   |   yes    | `1024`                                               | Size of vectors stored in `documents.embedding`. **Must** match your embedding model (`bge-m3`=1024).|
| `OLLAMA_BASE_URL` |    no    | `http://localhost:11434`                             | Base URL of the external Ollama server used for embeddings / chat models.                            |
| `EMBEDDING_MODEL` |    no    | `bge-m3`                                              | Ollama embedding model. Must produce vectors of size `EMBEDDING_DIM`.                                |

The application loads `.env` automatically (via `python-dotenv`). You can also
export the variables in your shell instead of using a file.

> **Changing the embedding model / dimensions:** `EMBEDDING_DIM` is baked into the
> `documents.embedding` column type at migration time. If you switch to a model
> with a different vector size, update `EMBEDDING_DIM` and run the migration
> against a fresh/empty database (or drop and recreate the `documents` table).

---

## 4. Run the schema migration

With the database running and `.env` configured, create all tables, indexes, the
pgvector extension, and the LangGraph checkpoint tables in one step:

```bash
# From the project root, with your virtualenv activated and deps installed
python -m db.migrate
```

This will:

1. Connect using `DATABASE_URL`.
2. `CREATE EXTENSION IF NOT EXISTS vector`.
3. Create the `sessions`, `messages`, `agents`, `agent_tools`, `links`, and
   `documents` tables (the `documents.embedding` column is sized from
   `EMBEDDING_DIM`), plus their indexes — including an **HNSW** cosine index on
   the embedding column.
4. Set up the LangGraph PostgreSQL checkpoint tables.

The migration is **idempotent** — it is safe to run again; existing objects are
left in place (`CREATE TABLE IF NOT EXISTS`).

---

## 5. Verify the setup

```bash
# Confirm the extension and tables exist
psql "$DATABASE_URL" -c '\dx'        # should list "vector"
psql "$DATABASE_URL" -c '\dt'        # should list sessions, messages, agents,
                                     # agent_tools, links, documents (+ checkpoints*)
```

For a full end-to-end check, run the bundled verification script. It exercises
every repository (sessions, agents, crawler queue, vector search) and the
FastAPI session/memory endpoints against your database — no Ollama required (a
fake embedder is injected) and it cleans up everything it creates:

```bash
python scripts/verify_db.py
```

You can now start the application as described in the [README](README.md):

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000   # backend
streamlit run app.py                              # UI (separate terminal)
```

---

## Troubleshooting

- **`could not connect to server` / connection refused** — Make sure PostgreSQL
  is running and listening on the host/port in `DATABASE_URL`
  (`pg_lsclusters`, `sudo service postgresql status`, or `docker ps`).
- **`type "vector" does not exist`** — The pgvector extension is not installed or
  not enabled in this database. Install the `postgresql-<ver>-pgvector` package
  and re-run `python -m db.migrate` (or enable it manually as in step 2).
- **`permission denied to create extension "vector"`** — Enable the extension as
  the `postgres` superuser:
  `sudo -u postgres psql -d gabriel -c 'CREATE EXTENSION IF NOT EXISTS vector;'`,
  then re-run the migration.
- **`password authentication failed`** — The credentials in `DATABASE_URL` do not
  match the role created in step 2. Update one to match the other.
- **Embedding dimension mismatch on insert** — `EMBEDDING_DIM` does not match the
  vector size produced by `EMBEDDING_MODEL`. Fix `EMBEDDING_DIM` and re-migrate a
  fresh database.
