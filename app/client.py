from elasticsearch import Elasticsearch

client = Elasticsearch("http://localhost:9200")

if __name__ == "__main__":
    print(client.info())