import csv
from elasticsearch import helpers
from app.client import client

INDEX = 'movies'
CSV_PATH = "data/movies.csv"

def read_movies(path):
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            yield {
                "_index": INDEX,
                "_id": str(i),
                "_source": {
                    "title": row["title"],
                    "overview": row["overview"],
                    "genres": row["genres"].split("|"),
                    "director": row["director"],
                    "year": int(row["year"]),
                    "rating": float(row["rating"]),
                },

            }

if __name__ == "__main__":
    success, errors = helpers.bulk(client, read_movies(CSV_PATH))
    client.indices.refresh(index=INDEX)
    print(f"Indexed {success} movies, errors: {errors}")