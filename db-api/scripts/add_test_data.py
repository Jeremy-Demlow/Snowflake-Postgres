#!/usr/bin/env python
"""Add test data to Postgres for CDC testing"""
import psycopg2
import os

host = os.environ['PG_HOST']
user = os.environ['PG_USER']
password = os.environ['PG_PASSWORD']

# Add to customer_a_db
conn_a = psycopg2.connect(host=host, port=5432, database='customer_a_db', user=user, password=password)
cur_a = conn_a.cursor()
cur_a.execute('SELECT MAX(user_id) FROM users')
max_a = cur_a.fetchone()[0]
cur_a.execute(
    'INSERT INTO users (user_id, name, email, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW()), (%s, %s, %s, NOW(), NOW()), (%s, %s, %s, NOW(), NOW()), (%s, %s, %s, NOW(), NOW()), (%s, %s, %s, NOW(), NOW())',
    (max_a+1, 'Production User A1', 'proda1@example.com', 
     max_a+2, 'Production User A2', 'proda2@example.com', 
     max_a+3, 'Production User A3', 'proda3@example.com', 
     max_a+4, 'Production User A4', 'proda4@example.com', 
     max_a+5, 'Production User A5', 'proda5@example.com')
)
conn_a.commit()
print(f'customer_a_db: Added 5 users (IDs {max_a+1}-{max_a+5})')
conn_a.close()

# Add to customer_b_db
conn_b = psycopg2.connect(host=host, port=5432, database='customer_b_db', user=user, password=password)
cur_b = conn_b.cursor()
cur_b.execute('SELECT MAX(user_id) FROM users')
max_b = cur_b.fetchone()[0]
cur_b.execute(
    'INSERT INTO users (user_id, name, email, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW()), (%s, %s, %s, NOW(), NOW()), (%s, %s, %s, NOW(), NOW())',
    (max_b+1, 'Production User B1', 'prodb1@example.com', 
     max_b+2, 'Production User B2', 'prodb2@example.com', 
     max_b+3, 'Production User B3', 'prodb3@example.com')
)
conn_b.commit()
print(f'customer_b_db: Added 3 users (IDs {max_b+1}-{max_b+3})')
conn_b.close()

print('\nDone - 8 new records added to Postgres')
