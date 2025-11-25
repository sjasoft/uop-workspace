import pytest
from uop.db.neo4j import adaptor
from uop.core.plugin_test.harness import Plugin

@pytest.fixture(scope="session")
def db_harness():
    """
    Pytest fixture to set up and tear down a Neo4j test database.
    """
    # Connect to the default 'neo4j' database
    db = adaptor.Neo4jUOP.make_named_database(
        "neo4j",
        uri="bolt://localhost:7687",
        user="neo4j",
        password="testpassword"
    )
    plug_in = Plugin(db)
    
    yield plug_in# Provide the database adapter instance to the tests
    
    # No need to drop the default database, just close the connection
    db.close()
