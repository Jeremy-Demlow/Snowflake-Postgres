#!/usr/bin/env python
import os
import sys
import subprocess

os.environ['PG_USER'] = 'snowflake_admin'
os.environ['PG_PASSWORD'] = '2YGJwLyFpYzctX775PKCuFEDTM1KXc86wrHhUZiahYpWQdZ9Gv4mJJmg0t5PXvIo'
os.environ['SNOWFLAKE_CONNECTION_NAME'] = 'myconnection'

result = subprocess.run(
    ['/Users/jdemlow/miniconda3/envs/snowflake-postgres/bin/python', '-m', 'pytest', '-v', '--tb=short'],
    cwd='/Users/jdemlow/github/Snowflake-Postgres/db-api',
    env=os.environ
)
sys.exit(result.returncode)
