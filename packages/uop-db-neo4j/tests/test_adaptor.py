from uop.core.plugin_testing.harness import test_general_db, db_harness
from uop.core.testing.random_data import random_data
from uop.core.testing.fixtures import db_tagged, db_grouped, db_related

# By importing these fixtures, pytest will automatically discover and use them.
# The `db_harness` fixture will be created using the `db_plugin` fixture
# defined in conftest.py. The `test_general_db` function will then be
# run with the fully configured harness.

def test_general_db(db_harness, random_data, db_tagged, db_grouped, db_related):
    test_general_db(db_harness, random_data, db_tagged, db_grouped, db_related)