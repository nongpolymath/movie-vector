## MovieVector: Text, Time, and Meaning in Movie Search
A small learning project: an Elasticsearch index of movies with a FastAPI backend. The idea is that how you index the data decides what you can ask of it, so the same movies are searchable three ways: by text (keyword search over title and overview), by time (a timeline grouped into eras), and by meaning (semantic "vibe" search over `all-MiniLM-L6-v2` embeddings). There are also per-genre stats, prefix autocomplete, and consistent error handling. It's meant for learning how indexing shapes queries, not for production.

### Requirements
Docker (for Elasticsearch) and Python 3.10+. Elasticsearch 8.15 runs single-node with security disabled: fine for local learning, not for anything networked.

### Setup
Start Elasticsearch, then the environment (Windows PowerShell):

    docker compose up -d
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

ES listens on http://localhost:9200 (confirm with `curl.exe http://localhost:9200`).

### Loading data
`data/movies.csv` is one movie per row (title, overview, genres, director, year, rating; genres pipe-separated). From the project root:

    python -m app.create_index   # (re)create the movies index + mapping
    python -m app.load_movies    # bulk-load every row

A field's type can't change on an existing index, so any mapping change means rerunning both.

### Running the API
    uvicorn app.api:app --reload   # interactive docs at http://localhost:8000/docs

### Endpoints
- `GET /health`: status object for liveness checks.
- `GET /movies/{movie_id}`: one movie by id, or 404.
- `GET /search`: full-text over title and overview. Params: q, genre, year_from, year_to, min_rating, page, size. Returns total and the current page, each result scored.
- `GET /stats/genres`: movies grouped by genre with count and average rating. Params: top, min_rating.
- `GET /suggest`: autocomplete; a partial q returns a few title/year matches. Needs title mapped search-as-you-type.

### Project layout
- `app/client.py`: shared Elasticsearch client every module imports.
- `app/create_index.py`: defines the mapping and creates the index.
- `app/load_movies.py`: bulk-loads the CSV.
- `app/api.py`: FastAPI app and all endpoints.
- `app/search.py`: scratch example queries against the client.
- `app/index_one_mov.py`: indexes one hardcoded movie (an early index/get step).
- `embedder/`: standalone serving container, a small FastAPI app loading `all-MiniLM-L6-v2` behind `POST /embed`. Its own image so `torch` stays out of the search API; ingest and the API both call it over HTTP.

### Architecture (target, next milestone)
TMDB feeds an ingestion script that pages and maps movies, then bulk-upserts into Elasticsearch behind a `movies` alias (so reindexes are a swap, not a rebuild). Embedding runs in its own CPU container, a small FastAPI app wrapping `sentence-transformers` (`all-MiniLM-L6-v2`), which keeps `torch` out of the search-API image. Ingest and the search API both reach it on `POST /embed`: ingest to embed overviews, the API to embed the incoming vibe query.

    TMDB  /discover/movie
          │
          ▼
    ┌─────────────────────────────┐        ┌──────────────────────────────┐
    │  app/tmdb_ingest.py          │        │  embedder  (own container)   │
    │  page · map · bulk-upsert    │─text──▶│  FastAPI · all-MiniLM-L6-v2  │
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

Search modes: keyword (`/search`) is a bool query over title+overview; timeline (`/search/timeline`) is aggregation into era buckets with top_hits per era; vibe (`/search/vibe`, the ML feature) embeds the query via the embedder, then kNN over overview_vector. Everything runs in Docker on a laptop, CPU only.

### Design alternative: TEI
The embedder is swappable: anything answering `POST /embed` works, so ingest and search code never change. The chosen build is a small in-repo FastAPI app (full control, uniform stack, most to learn from). The alternative is HuggingFace Text Embeddings Inference (TEI), a prebuilt server you run instead of writing one:

    embedder:
      image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
      command: --model-id sentence-transformers/all-MiniLM-L6-v2

TEI pros: fast on CPU (Rust, dynamic batching), built-in health/metrics/warmup, zero serving code, MiniLM/BERT first-class. TEI cons: an opaque binary you adapt to rather than own, less serving insight, one more image to pin, and a throughput edge that's irrelevant at this scale. Start with the FastAPI embedder; because the contract is identical, moving to TEI later is a compose change, not a code change.

### Roadmap: Milestone 4
Expand from the CSV to TMDB and add two search modes: an aggregation timeline and a semantic vibe search. Stand up the embedder first (both features call it), then ingestion (both need real data). Each part runs on its own.

Part 1, TMDB ingestion + alias. Page `/discover/movie` by popularity (cap ~2-5k), use the TMDB id as `_id` so reloads are idempotent upserts, map release_date as a real date (keep year), read/write through a `movies` alias on `movies_v1`, and yield each page into `helpers.bulk`.

Part 2, timeline search. `GET /search/timeline?q=`: bool query for the trope plus a range aggregation into fixed era buckets (1950s, 60s, ...), with top_hits (size 1, by rating) per bucket. Hand-curated eras can come later.

Part 3, vibe search (the ML feature). Add `overview_vector` dense_vector(384, cosine) and reindex, have the loader batch-call the embedder to vectorize overviews, and expose `GET /search/vibe?q=` as kNN (k=10, num_candidates=100) reusing MovieResult. The API embeds the query via the same service.

Out of scope: no CLIP, raw BERT, or fine-tuning; one CPU FastAPI embedder (TEI is the documented alternative, not both); no GPU, autoscaling, or queue; overviews only, no review embeddings; pure kNN first, no hybrid/RRF.
