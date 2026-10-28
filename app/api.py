from elasticsearch import BadRequestError, NotFoundError
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse, RedirectResponse
from app.client import client
from pydantic import BaseModel

INDEX = "movies"

app = FastAPI(title="Movie Search API", version="0.1.0")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

class MovieResult(BaseModel):
    id: str
    title: str
    year: float
    rating: float
    score: float | None = None
    overview: str | None = None

class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    results: list[MovieResult]

class GenreStat(BaseModel):
    genre: str
    count: int
    avg_rating: float | None = None

class GenreStatsResponse(BaseModel):
    total_movies: int
    stats: list[GenreStat]

class Suggestion(BaseModel):
    title: str
    year: int

# --- Global policy: applies to EVERY endpoint automatically ---

@app.exception_handler(ConnectionError)
async def es_unavailable(request, exc):
    # ES is down/unreachable — transient, client may retry. Expected, so no traceback.
    return JSONResponse(status_code=503, content={"detail": "Search backend unavailable"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/movies/{movie_id}")
def get_movie(movie_id: int):
    try:
        resp = client.get(index=INDEX, id=movie_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Movie not found")
    return resp["_source"]


@app.get("/search", response_model= SearchResponse)
def search_movie(
    q: str | None = None,
    genre: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    min_rating: float | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
):
    must = []
    if q:
        must.append({"multi_match": {"query": q, "fields": ["title^3", "overview"]}})

    filters = []
    if genre:
        filters.append({"term": {"genres": genre}})
    if min_rating is not None:
        filters.append({"range": {"rating": {"gte": min_rating}}})
    if year_from is not None or year_to is not None:
        bounds = {}
        if year_from is not None:
            bounds["gte"] = year_from
        if year_to is not None:
            bounds["lte"] = year_to
        filters.append({"range": {"year": bounds}})

    query = {"bool": {"must": must, "filter": filters}}

    try:
        resp = client.search(
            index=INDEX,
            query=query,
            from_=(page - 1) * size,
            size=size,
        )
    except BadRequestError as e:
        raise HTTPException(status_code=400, detail=f"Invalid query: {e}")

    return SearchResponse(
    total=resp["hits"]["total"]["value"],
    page=page,
    size=size,
    results=[
        MovieResult(
            id=hit["_id"],
            score=hit["_score"],
            **hit["_source"],
        )
        for hit in resp["hits"]["hits"]
    ],
)

    # return {"total": resp["hits"]["total"]["value"], "results": [h for h in resp["hits"]["hits"]]}

@app.get("/stats/genres")
def movie_stats(top: int = Query(20, ge=1, le=100), min_rating: float = 0.0):
    query = {"range": {"rating": {"gte": min_rating}}} if min_rating else {"match_all": {}}
    resp = client.search(index=INDEX, size=0, query=query, aggs={
        "by_genre": {
            "terms": {"field": "genres", "size": top},
            "aggs": {"avg_rating": {"avg": {"field": "rating"}}},
        }},)
    buckets = resp["aggregations"]["by_genre"]["buckets"]
    stats = [
        GenreStat(
            genre=b["key"],
            count=b["doc_count"],
            avg_rating=round(b["avg_rating"]["value"], 2),
        )
        for b in buckets
    ]

    return GenreStatsResponse(
        total_movies=resp["hits"]["total"]["value"],
        stats=stats,
    )

@app.get("/suggest")
def suggest(q: str = Query(...,min_length=1), size: int = Query(5, ge=1, le=10)):
    resp = client.search(index=INDEX, size=size , 
                         source = ["title", "year"],
                         query = {
                             "multi_match": {
                                 "query": q,
                                 "type": "bool_prefix",
                                 "fields": ["title", "title._2gram", "title._3gram"],
        }},)
    return [Suggestion(title=h["_source"]["title"], year=h["_source"]["year"])
            for h in resp["hits"]["hits"]]