# Movie Search

A small project exploring Elasticsearch with a FastAPI backend with search, lookup, stats, autocomplete, and consistent error handling. It indexes movies and exposes HTTP endpoints over them: 
full-text search with filters, per-genre stats, and prefix autocomplete. The aim is to learn how indexing 
shapes what queries are possible, not to be a production service.

## Requirements

Docker (for Elasticsearch) and Python 3.10+. Elasticsearch 8.15 runs single-node
with security disabled: fine for local learning, not for anything networked.

## Setup

Start Elasticsearch, then set up the environment (Windows PowerShell):

    docker compose up -d
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

Elasticsearch listens on http://localhost:9200; confirm with
`curl.exe http://localhost:9200`.

## Loading data

`data/movies.csv` has one movie per row (columns: title, overview, genres,
director, year, rating; genres pipe-separated in one cell). From the project root:

    python -m app.create_index   # (re)create the movies index with its mapping
    python -m app.load_movies    # bulk-load every row

A field's type can't change on an existing index, so any mapping change means
rerunning both.

## Running the API

    uvicorn app.api:app --reload
Interactive docs: http://localhost:8000/docs.

## Endpoints

- `GET /health` — status object, for liveness checks.
- `GET /movies/{movie_id}` — one movie by id, or 404.
- `GET /search` — full-text search over title and overview. Params: q, genre,
  year_from, year_to, min_rating, page, size. Returns total matches and the
  current page, each result scored.
- `GET /stats/genres` — movies grouped by genre with count and average rating.
  Params: top (how many genres), min_rating (restrict to higher-rated).
- `GET /suggest` — autocomplete; a partial q returns a few matches as title and
  year. Relies on title being mapped search-as-you-type.

## Project layout

- `app/client.py` — shared Elasticsearch client every module imports.
- `app/create_index.py` — defines the mapping and creates the index.
- `app/load_movies.py` — bulk-loads the CSV.
- `app/api.py` — FastAPI app and all endpoints above.
- `app/search.py` — scratch script of example queries against the client.
- `app/index_one_mov.py` — indexes one hardcoded movie, an early index/get step.

## Architecture (target — Next Milestone)

TMDB feeds an ingestion script that pages, maps, and embeds overviews, then bulk-
upserts into Elasticsearch behind a `movies` alias (so reindexes are a swap, not a
rebuild). The embedding model runs in-process on CPU. FastAPI queries the alias
and serves keyword, timeline, and vibe search to HTTP clients through the one
shared client.

    TMDB  /discover/movie
          │
          │  app/tmdb_ingest.py — page, map, embed, bulk-upsert (_id = TMDB id)
          │  sentence-transformers all-MiniLM-L6-v2  (CPU, in-process)
          ▼
    ┌─────────────────────────────┐        ┌────────────────────────────┐
    │   Elasticsearch  8.15 :9200 │ query  │   FastAPI  (app/api.py)     │
    │                             │◀──────▶│   uvicorn  :8000            │
    │   alias movies → movies_v1  │        │                             │
    │   fields: title (sayt),     │        │   /search          (bool)   │
    │     overview, genres, year, │        │   /search/timeline (aggs)   │
    │     release_date (date),    │        │   /search/vibe     (knn)    │
    │     rating,                 │        │   /stats/genres, /suggest,  │
    │     overview_vector         │        │   /movies/{id}, /health     │
    │       (dense_vector 384,cos)│        │                             │
    └─────────────────────────────┘        └────────────────────────────┘
              ▲                                          ▲
              │  app/client.py (shared client)     HTTP  │  browser / curl
              └──────────────────────────────────────────┘

    Everything runs in Docker on a laptop — CPU only, no GPU.

## Roadmap — Milestone 4

Expand the dataset from the CSV to TMDB and add two search modes: a cheap
aggregation-based timeline and a semantic "vibe" search. Three focused parts,
each runnable on its own.

Part 1 — TMDB ingestion + alias (do first; both features need real data):
- [ ] Page through `/discover/movie` sorted by popularity; cap at ~2–5k movies.
- [ ] Use the TMDB movie id as `_id` so reloads are idempotent upserts.
- [ ] Map `release_date` to a real `date` field; keep `year` too.
- [ ] Read/write through a `movies` alias pointing at `movies_v1`.
- [ ] Yield each page into `helpers.bulk` (reuse the generator pattern).

Part 2 — Timeline search (the cheap win, pure aggregation):
- [ ] `GET /search/timeline?q=` — bool query for the trope + range agg into fixed
      era buckets (1950s, 60s, …).
- [ ] `top_hits` (size 1, sorted by rating) per bucket for the standout movie.
- [ ] Later (optional): hand-curated historical eras (WWII, etc.).

Part 3 — Vibe search (the ML feature, do last):
- [ ] Add `overview_vector` `dense_vector(dims=384, cosine)` to the mapping; reindex.
- [ ] Batch-encode overviews with `all-MiniLM-L6-v2` in the loader.
- [ ] `GET /search/vibe?q=` — kNN (`k=10`, `num_candidates=100`), reuse `MovieResult`.

Out of scope:
- No CLIP or raw BERT, and no fine-tuning — MiniLM off the shelf is enough.
- Model in-process; no separate embedding service or queue.
- CPU torch only; no GPU/CUDA image.
- Overviews only — no review embeddings on the first pass.
- Pure kNN first; no hybrid/RRF until it works.
