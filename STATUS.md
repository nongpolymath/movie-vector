# MovieVector Project Status

Last updated: 2026-10-28

Snapshot of what's built, scaffolded, and planned. Full overview in [README.md](README.md).

The keyword search backend works end to end. The TMDB data pipeline and the two
richer search modes (timeline, semantic vibe) are designed but not yet built.

## Status at a glance

| Area | Status |
|------|--------|
| Elasticsearch infra (Docker) | Done |
| Index mapping | Done |
| CSV bulk loading | Done |
| Core search API | Done |
| TMDB ingestion | Planned |
| Embedder service | Planned |
| Airflow + Kafka sync | Planned |
| Timeline search | Planned |
| Vibe search | Planned |

## Done

Infrastructure
- `docker-compose.yml`: single-node Elasticsearch 8.15 on port 9200, security off.
- `app/client.py`: shared Elasticsearch client imported by every module.

Index and data
- `app/create_index.py`: type-aware mapping. `title` as search_as_you_type,
  `overview` as text, `genres` and `director` as keyword, `year` as integer,
  `rating` as float. Drops and recreates on rerun since mappings are immutable.
- `app/load_movies.py`: streams `data/movies.csv` through a generator into
  `helpers.bulk`, splitting pipe-separated genres and casting types.

API (`app/api.py`), five endpoints with Pydantic response models and error handling:

| Endpoint | What it does | ES features |
|----------|--------------|-------------|
| `GET /health` | Liveness check | none |
| `GET /movies/{id}` | Fetch one movie, 404 if missing | get, NotFoundError |
| `GET /search` | Full-text over title and overview plus genre/year/rating filters, paginated | multi_match, bool, range, term |
| `GET /stats/genres` | Per-genre counts and average rating | terms agg + nested avg agg |
| `GET /suggest` | Prefix autocomplete | bool_prefix multi_match |

Also handled: ConnectionError returns 503, BadRequestError returns 400, root
redirects to `/docs`, favicon returns 204, pagination bounds validated.

Learning scripts kept on purpose:
- `app/index_one_mov.py`: indexes one hardcoded movie.
- `app/search.py`: scratchpad of example queries.

## Scaffolded but not built

Documented in the README architecture, no code yet:
- `embedder/`: FastAPI container wrapping all-MiniLM-L6-v2, exposing `POST /embed`.
- `app/tmdb_sync/`: Airflow DAG plus Kafka producer and consumer.
- `overview_vector`: dense_vector(384, cosine) field, added by reindex and alias swap.

## Planned (Milestone 4)

Build the embedder first since both search modes depend on it.

Part 1, TMDB sync. A DAG polls TMDB `/movie/changes` and produces changed ids to
Kafka. A consumer fetches each movie, uses the TMDB id as `_id` for idempotent
upserts, maps release_date as a date, and reads/writes through a `movies` alias.
Failures go to a dead-letter topic. A periodic DAG does the rebuild and swap.

Part 2, timeline search. `GET /search/timeline?q=`: bool query for the trope plus
a range aggregation into fixed era buckets, top_hits (size 1, by rating) per bucket.

Part 3, vibe search. Add `overview_vector` and reindex. The worker batch-calls the
embedder to vectorize overviews. Expose `GET /search/vibe?q=` as kNN (k=10,
num_candidates=100). The API embeds the query via the same service.

Out of scope: no CLIP, raw BERT, or fine-tuning; one CPU embedder; no GPU or
autoscaling; overviews only; pure kNN first, no hybrid/RRF.

## Running what exists today

```powershell
docker compose up -d

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m app.create_index
python -m app.load_movies

uvicorn app.api:app --reload
```

ES listens on http://localhost:9200. API docs at http://localhost:8000/docs.
A mapping change means rerunning create_index and load_movies.
