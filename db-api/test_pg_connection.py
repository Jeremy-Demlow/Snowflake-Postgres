#!/usr/bin/env python
import os
os.environ['PG_USER'] = 'snowflake_admin'
os.environ['PG_PASSWORD'] = '2YGJwLyFpYzctX775PKCuFEDTM1KXc86wrHhUZiahYpWQdZ9Gv4mJJmg0t5PXvIo'
os.environ['SNOWFLAKE_CONNECTION_NAME'] = 'myconnection'

import psycopg2
conn = psycopg2.connect(
    host='htsfodr735dklagr4zqg4uu34y.sfsenorthamerica-demo-jdemlow.us-west-2.aws.postgres.snowflake.app',
    port=5432,
    dbname='customer_a_db',
    user=os.environ['PG_USER'],
    password=os.environ['PG_PASSWORD'],
    sslmode='require',
)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM public.users')
print(f'Users count: {cur.fetchone()[0]}')
cur.close()
conn.close()
print('Postgres connection OK!')
