#!/usr/bin/env python
import os
import sys

os.environ['PG_USER'] = 'snowflake_admin'
os.environ['PG_PASSWORD'] = '2YGJwLyFpYzctX775PKCuFEDTM1KXc86wrHhUZiahYpWQdZ9Gv4mJJmg0t5PXvIo'
os.environ['SNOWFLAKE_CONNECTION_NAME'] = 'myconnection'

sys.path.insert(0, '/Users/jdemlow/github/Snowflake-Postgres/db-api')

import pytest
sys.exit(pytest.main(['-v', '-s', 'tests/test_integration.py']))
