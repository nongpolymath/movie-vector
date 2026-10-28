from app.client import client

INDEX = 'movies'

MAPPINGS = {
    'properties': {
        'title': {'type': 'search_as_you_type'},
        'overview': {'type': 'text'},
        'genres': {'type': 'keyword'},
        'director': {'type': 'keyword'}, 
        'year': {'type': 'integer'}, 
        'rating': {'type': 'float'}
    }
}

if __name__ == '__main__':
    if client.indices.exists(index=INDEX):
        client.indices.delete(index=INDEX)
    client.indices.create(index = INDEX, mappings= MAPPINGS)
    print(f"Created index '{INDEX}'")
    print(client.indices.analyze(index="movies", field="overview", text="Running Astronauts in space"))
    print(client.indices.analyze(index="movies", field="genres", text="Science Fiction"))