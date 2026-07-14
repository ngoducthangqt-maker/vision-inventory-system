# inventory-service

A standalone **inventory management microservice** built with **FastAPI + SQLAlchemy 2.0 + PostgreSQL**, structured following **Clean Architecture**.

It exposes a full CRUD API (plus `restock` / `consume` domain operations) for the `inventory_item` resource and ships with a production-ready, multi-stage Dockerfile.

---

## Architecture

```
inventory-service/
├── app/
│   ├── main.py                         # FastAPI entry point (application factory + lifespan)
│   ├── dependencies.py                 # Composition root / DI wiring
│   ├── core/                           # Cross-cutting concerns
│   │   ├── config.py                   # pydantic-settings (env-driven config)
│   │   └── database.py                 # async SQLAlchemy engine + session
│   ├── domain/                         # ◀ Enterprise business rules (no framework deps)
│   │   ├── entities/
│   │   │   └── inventory_item.py       # Pure dataclass entity + domain methods
│   │   └── repositories/
│   │       └── inventory_item_repository.py   # Abstract repository contract
│   ├── use_cases/                      # ◀ Application business rules
│   │   └── inventory_item_use_cases.py # Orchestrates entities via repo contract
│   ├── infrastructure/                 # ◀ Frameworks & drivers (depends inward)
│   │   ├── models/
│   │   │   └── inventory_item_model.py # SQLAlchemy ORM model
│   │   └── repositories/
│   │       └── inventory_item_repository_impl.py  # PostgreSQL repo implementation
│   └── presentation/                   # ◀ HTTP delivery (FastAPI)
│       ├── schemas/
│       │   └── inventory_item_schema.py# Pydantic v2 request/response DTOs
│       └── api/
│           ├── router.py               # Aggregates v1 routers
│           └── v1/
│               └── inventory_items.py  # CRUD + restock/consume endpoints
├── tests/
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

### The dependency rule

Dependencies point **inward**:

```
presentation ──▶ use_cases ──▶ domain ◀── infrastructure
```

- The **domain** layer (entities + repository *contracts*) has zero framework imports.
- **Use cases** depend only on the domain contract, never on SQLAlchemy or FastAPI.
- **Infrastructure** (SQLAlchemy/Postgres) implements the domain contract.
- **Presentation** (FastAPI routes) calls use cases through DI.

This means the business logic is fully unit-testable without a database or HTTP server.

---

## API reference

Base URL: `/api/v1`

| Method   | Path                              | Description                          |
|----------|-----------------------------------|--------------------------------------|
| `POST`   | `/inventory-items`                | Create a new inventory item          |
| `GET`    | `/inventory-items`                | List items (filter: `category`, `low_stock_only`, pagination `skip`/`limit`) |
| `GET`    | `/inventory-items/{id}`           | Retrieve a single item               |
| `PATCH`  | `/inventory-items/{id}`           | Partially update an item             |
| `DELETE` | `/inventory-items/{id}`           | Delete an item (204)                 |
| `POST`   | `/inventory-items/{id}/restock`   | Increase stock (`{"amount": N}`)     |
| `POST`   | `/inventory-items/{id}/consume`   | Decrease stock (`{"amount": N}`)     |
| `GET`    | `/health`                         | Liveness probe                       |
| `GET`    | `/docs`                           | Swagger UI                           |

---

## Getting started (local)

```bash
cd inventory-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit POSTGRES_* values
uvicorn app.main:app --reload --port 8000
```

> In non-production mode the service auto-creates tables on startup (`init_db`). For production use Alembic migrations.

---

## Running with Docker

```bash
docker build -t inventory-service:latest .

docker run --rm -p 8000:8000 \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_USER=inventory \
  -e POSTGRES_PASSWORD=inventory \
  -e POSTGRES_DB=inventory_db \
  inventory-service:latest
```

### With docker-compose (service + Postgres)

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: inventory
      POSTGRES_PASSWORD: inventory
      POSTGRES_DB: inventory_db
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  inventory-service:
    build: .
    depends_on: [postgres]
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_USER: inventory
      POSTGRES_PASSWORD: inventory
      POSTGRES_DB: inventory_db
      ENVIRONMENT: production
    ports: ["8000:8000"]

volumes:
  pgdata:
```

---

## Configuration

All settings come from environment variables (see `.env.example`). Key ones:

| Variable            | Default        | Description                          |
|---------------------|----------------|--------------------------------------|
| `POSTGRES_HOST`     | `localhost`    | Database host                        |
| `POSTGRES_PORT`     | `5432`         | Database port                        |
| `POSTGRES_USER`     | `inventory`    | DB user                              |
| `POSTGRES_PASSWORD` | `inventory`    | DB password                          |
| `POSTGRES_DB`       | `inventory_db` | DB name                              |
| `ENVIRONMENT`       | `development`  | `development` auto-creates tables    |
| `CORS_ORIGINS`      | `*`            | Comma-separated allowed origins      |
