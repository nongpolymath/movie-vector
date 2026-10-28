from app.client import client

INDEX = "movies"

def show(query, **kwargs):
    resp = client.search(index=INDEX, query=query, **kwargs)
    print(f"{resp['hits']['total']['value']} hits")
    for hit in resp["hits"]["hits"]:
        m = hit["_source"]
        print(f"{hit['_score']} {m['title']} ({m['year']}) {m['rating']}    {hit['_source']}")
    

if __name__ == "__main__":
    show({"match": {"overview": "space"}})
    show({"multi_match": {"query": "dreams", "fields": ["title^3", "overview"]}})
    show({
    "bool": {
        "must":   [{"match": {"overview": "earth"}}],                 
        "filter": [{"term": {"genres": "Science Fiction"}}],          
    }
    })
    show(
    {"bool": {"filter": [
        {"term": {"genres": "Science Fiction"}},
        {"range": {"rating": {"gte": 8.5}}},
    ]}},
    sort=[{"rating": "desc"}],
    )
    print(client.indices.analyze(index="movies", field="genres", text="Science Fiction"))
    print(" -----------------------------------------------------------------------------")
    show({"match": {"overview": "space astronauts"}})
    show({"multi_match": {"query": "dreams", "fields":["title^3", "overview"]}})
    print(" -----------------------------------------------------------------------------")
    show({"term":{"genres": "Drama"}})
    show({"terms":{"genres":["Science Fiction", "Drama"]}})
    print(" ---------------------------------------------------------------------------------")
    show({"range": {"rating": {"gte": "8"}}})
    show({"range": {"year":{"gte": "2000", "lte": 2010}}})
    print(" ---------------------------------------------------------------------------------")
    show({"exists":{"field": "director"}})
    print(" ---------------------------------------------------------------------------------")
    show({"bool": {"filter":[
        {"term": {"genres": "Drama"}},
        {"range":{"year":{"gte": 2000}}},
        {"range":{"rating":{"gte":8}}}
    ]}},)