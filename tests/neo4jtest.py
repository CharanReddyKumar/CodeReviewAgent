from neo4j import GraphDatabase

URI = "neo4j://127.0.0.1:7687"  # you can also use "bolt://127.0.0.1:7687"
USER = "neo4j"
PASSWORD = "12345678"      # same as you used in cypher-shell
DB = "neo4j"            # or whatever the DB is called in Desktop

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

with driver.session(database=DB) as session:
    result = session.run("RETURN 1 AS n")
    print(result.single()["n"])

driver.close()
