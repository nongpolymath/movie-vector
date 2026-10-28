## MovieVector: Text, Time, and Meaning in Movie Search
A learning project with a production-inspired backend, scaled to one laptop. Movies sit in an Elasticsearch index behind a FastAPI service, searchable three ways by how they're indexed: text (keyword over title and overview), time (a timeline grouped into eras), and meaning (semantic "vibe" search over `all-MiniLM-L6-v2` embeddings). Plus per-genre stats, prefix autocomplete, and consistent errors.

The point is learning how indexing shapes queries while practising real architecture: Airflow schedules the sync, Kafka decouples the stages, a separate container serves the model, Elasticsearch queries behind an alias. All open source, so the production-inspired design costs nothing and locks in nothing. Not a production deployment (single node, security off); just production-shaped, shrunk to a laptop.

### Stack
- Elasticsearch 8.15: index and query engine. Single-node, security off: fine locally, not networked.
- FastAPI + uvicorn: the search API.
- Embedder: a small FastAPI container wrapping `all-MiniLM-L6-v2`, its own image so `torch` stays out of the API.
- Airflow: schedules the TMDB sync.
- Kafka: carries changed movie ids from poll to ingest worker.
- Docker Compose: runs the stack on one machine.

Requirements: Docker and Python 3.10+.

### Built vs planned
Built: the mapping, CSV bulk-load, and core API (`/health`, `/movies/{id}`, `/search`, `/stats/genres`, `/suggest`). Planned (Milestone 4): TMDB ingestion, the embedder, the Airflow + Kafka sync, and the timeline and vibe modes. Architecture below is the target; the setup steps run what exists today.

### Setup
Start the stack, then the Python env (Windows PowerShell):

    docker compose up -d
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

ES listens on http://localhost:9200 (`curl.exe http://localhost:9200`).

### Loading data
Today the index loads from `data/movies.csv` (one movie per row: title, overview, genres, director, year, rating; genres pipe-separated):

    python -m app.create_index   # (re)create the movies index + mapping
    python -m app.load_movies    # bulk-load every row

A field's type can't change in place, so a mapping change means rerunning both. The target pipeline swaps this CSV load for the TMDB sync (below), same index and alias.

### Running the API
    uvicorn app.api:app --reload   # docs at http://localhost:8000/docs

### Endpoints
- `GET /health`: liveness status.
- `GET /movies/{movie_id}`: one movie by id, or 404.
- `GET /search`: full-text over title and overview. Params: q, genre, year_from, year_to, min_rating, page, size. Returns total and the scored page.
- `GET /stats/genres`: movies per genre with count and average rating. Params: top, min_rating.
- `GET /suggest`: autocomplete; a partial q returns a few title/year matches.
- `GET /search/timeline` (planned): trope query plus era-bucket aggregation.
- `GET /search/vibe` (planned): semantic kNN over overview embeddings.

### Project layout
- `app/client.py`: shared Elasticsearch client.
- `app/create_index.py`: mapping + index creation.
- `app/load_movies.py`: bulk-loads the CSV.
- `app/api.py`: FastAPI app and endpoints.
- `app/search.py`: scratch example queries.
- `app/index_one_mov.py`: indexes one hardcoded movie (early index/get step).
- `embedder/` (planned): serving container for `all-MiniLM-L6-v2` behind `POST /embed`; sync worker and API call it over HTTP.
- `app/tmdb_sync/` (planned): Airflow DAG plus Kafka producer (poll) and consumer (ingest worker).

### Architecture (target)
Airflow schedules the sync. Each run polls TMDB `/movie/changes` and produces the changed ids to Kafka; a worker consumes them, fetches each movie (`GET /movie/{id}`), embeds the overview, and bulk-upserts into Elasticsearch behind a `movies` alias (reindex is a swap, not a rebuild). Failures go to a dead-letter topic; Airflow also runs the periodic rebuild-and-swap. The embedder is its own CPU container wrapping `all-MiniLM-L6-v2`, keeping `torch` out of the API; the API embeds vibe queries via the same `POST /embed`.

    Airflow (scheduler, own container)
      │  cadence:  poll changes  +  periodic reconcile (rebuild + alias swap)
      ▼
    Kafka topic: changes  ◀──changed ids──  GET TMDB /movie/changes
      │  consume
      ▼
    ┌─────────────────────────────┐        ┌──────────────────────────────┐
    │  sync worker (consumer)      │        │  embedder  (own container)   │
    │  fetch · map · upsert        │─text──▶│  FastAPI · all-MiniLM-L6-v2  │
    │  (_id = TMDB id)             │◀──vec──│  POST /embed {text}→384-d    │
    └─────────────────────────────┘        └──────────────────────────────┘
          │                                       ▲        │
          │ bulk-upsert                     text  │        │ vector
          ▼                                       │        ▼
    ┌─────────────────────────────┐        ┌──────────────────────────────┐
    │   Elasticsearch  8.15 :9200 │ query  │   FastAPI  (app/api.py)      │
    │   alias movies → movies_v1  │◀──────▶│   uvicorn  :8000             │
    │   overview_vector           │        │   /search          keyword   │
    │     (dense_vector 384,cos)  │        │   /search/timeline era aggs  │
    │   + title, overview, genres,│        │   /search/vibe  ML semantic  │
    │     year, release_date,     │        │   /stats/genres, /suggest,   │
    │     rating                  │        │   /movies/{id}, /health      │
    └─────────────────────────────┘        └──────────────────────────────┘
                                                   ▲
                                             HTTP  │  browser / curl

Modes: keyword is a bool query over title+overview; timeline aggregates into era buckets with top_hits per era; vibe embeds the query, then kNN over overview_vector. All Docker, laptop, CPU only.

### Keeping in sync with TMDB
TMDB keeps changing, so ingest reruns to stay current. Airflow runs the schedule (retriable, observable, re-triggerable) instead of a bare cron job. Each run polls `/movie/changes`, produces the ids to Kafka, and a worker consumes, fetches, embeds, and upserts by TMDB id. Kafka decouples the steps: failures go to a dead-letter topic instead of stalling the run, and workers scale out.

What a run does, simplest to smartest:
- Reload everything. Simplest; can't drop deleted movies.
- Rebuild and swap. Fresh index, then flip the alias; clears deletions.
- Fetch only changes. The default; updates just the day's changes, cheapest.

Fetch-only-changes is the steady state; a periodic rebuild-and-swap clears drift and deletes.

### Design alternative: TEI
The embedder is swappable: anything answering `POST /embed` works, so ingest and search code never change. The build here is a small in-repo FastAPI app (full control, uniform stack, most to learn from). The alternative is HuggingFace Text Embeddings Inference (TEI), a prebuilt server:

    embedder:
      image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
      command: --model-id sentence-transformers/all-MiniLM-L6-v2

TEI: fast on CPU, built-in health/metrics, zero serving code, but an opaque binary and one more image to pin, with a throughput edge that's irrelevant at this scale. Start with the FastAPI embedder; the identical contract makes a later switch a compose change, not a code change.

### Roadmap: Milestone 4
Expand from CSV to TMDB and add two search modes (timeline, vibe). Stand up the embedder first (both features call it), then ingestion. Each part runs on its own.

Part 1, TMDB sync (Airflow + Kafka). A DAG polls `/movie/changes` on a cadence and produces changed ids to Kafka; a consumer fetches each movie, uses the TMDB id as `_id` for idempotent upserts, maps release_date as a date (keep year), and reads/writes through a `movies` alias on `movies_v1`. A periodic DAG does the rebuild-and-swap.

Part 2, timeline search. `GET /search/timeline?q=`: bool query for the trope plus a range aggregation into fixed era buckets, top_hits (size 1, by rating) per bucket.

Part 3, vibe search. Add `overview_vector` dense_vector(384, cosine) and reindex, have the worker batch-call the embedder to vectorize overviews, and expose `GET /search/vibe?q=` as kNN (k=10, num_candidates=100). The API embeds the query via the same service.

Out of scope: no CLIP, raw BERT, or fine-tuning; one CPU embedder (TEI is the alternative, not both); no GPU or autoscaling; overviews only; pure kNN first, no hybrid/RRF.
