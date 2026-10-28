from app.client import client

INDEX = 'movies'

movie = {
    "title": "Inception",
    "overview": "A thief who steals secrets by entering people's dreams is offered a chance to plant an idea instead.",
    "genres": ["Action", "Science Fiction", "Thriller"],
    "director": "Christopher Nolan",
    "year": 2010,
    "rating": 8.8,
}

if __name__ == "__main__":
    resp = client.index(index=INDEX, id='1', document=movie)
    client.indices.refresh(index=INDEX)
    print(client.search(index=INDEX, query={"match": {"title": "inception"}})["hits"]["total"])

    print(resp['result'])
    doc = client.get(index=INDEX, id='1')
    print(doc["_source"])
