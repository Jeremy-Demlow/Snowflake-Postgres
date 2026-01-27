#!/usr/bin/env python
"""
Generate realistic CDC test data with INSERTs and UPDATEs.
Matches actual Postgres schema.
"""
import os
import random
import time

import psycopg2

HOST = os.environ.get('PG_HOST')
USER = os.environ.get('PG_USER', 'snowflake_admin')
PASSWORD = os.environ.get('PG_PASSWORD')

DATABASES = ['customer_a_db', 'customer_b_db']

def get_conn(db):
    return psycopg2.connect(host=HOST, port=5432, database=db, user=USER, password=PASSWORD)

def generate_changes(num_inserts=1000, num_updates=500):
    """Generate INSERTs and UPDATEs across all tables."""
    
    print("=" * 70)
    print(f"GENERATING TEST DATA")
    print(f"  INSERTs: {num_inserts} per table")
    print(f"  UPDATEs: {num_updates} per table")
    print("=" * 70)
    
    for db in DATABASES:
        print(f"\n[{db}]")
        conn = get_conn(db)
        cur = conn.cursor()
        
        cur.execute("SELECT COALESCE(MAX(user_id), 0) FROM users")
        max_user_id = cur.fetchone()[0]
        
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM orders")
        max_order_id = cur.fetchone()[0]
        
        cur.execute("SELECT COALESCE(MAX(payment_id), 0) FROM payments")
        max_payment_id = cur.fetchone()[0]
        
        cur.execute("SELECT COALESCE(MAX(product_id), 0) FROM products")
        max_product_id = cur.fetchone()[0]
        
        cur.execute("SELECT COALESCE(MAX(inventory_id), 0) FROM inventory")
        max_inventory_id = cur.fetchone()[0]
        
        print(f"  Starting IDs: users={max_user_id}, orders={max_order_id}, products={max_product_id}")
        
        print(f"  Inserting {num_inserts} users...")
        start = time.time()
        for i in range(num_inserts):
            uid = max_user_id + i + 1
            cur.execute(
                "INSERT INTO users (user_id, name, email, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                (uid, f'Batch User {uid}', f'batch{uid}@test.com')
            )
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Inserting {num_inserts} orders...")
        start = time.time()
        for i in range(num_inserts):
            oid = max_order_id + i + 1
            cur.execute(
                "INSERT INTO orders (id, user_id, amount, status, order_date, created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW(), NOW())",
                (oid, random.randint(1, max_user_id), round(random.uniform(10, 500), 2), random.choice(['pending', 'completed', 'shipped']))
            )
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Inserting {num_inserts} payments...")
        start = time.time()
        for i in range(num_inserts):
            pid = max_payment_id + i + 1
            cur.execute(
                "INSERT INTO payments (payment_id, order_id, amount, method, status, processed_at, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
                (pid, random.randint(1, max_order_id), round(random.uniform(10, 500), 2), 
                 random.choice(['credit_card', 'paypal', 'bank_transfer']), 
                 random.choice(['pending', 'completed', 'failed']))
            )
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Inserting {num_inserts} products...")
        start = time.time()
        for i in range(num_inserts):
            pid = max_product_id + i + 1
            cur.execute(
                "INSERT INTO products (product_id, name, description, price, category, stock_quantity, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
                (pid, f'Product {pid}', f'Description for product {pid}', 
                 round(random.uniform(5, 200), 2), 
                 random.choice(['electronics', 'clothing', 'home', 'sports']),
                 random.randint(0, 1000))
            )
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Inserting {num_inserts} inventory records...")
        start = time.time()
        for i in range(num_inserts):
            iid = max_inventory_id + i + 1
            cur.execute(
                "INSERT INTO inventory (inventory_id, product_id, warehouse_code, quantity, last_restocked, created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW(), NOW())",
                (iid, random.randint(1, max_product_id), 
                 random.choice(['WH-A', 'WH-B', 'WH-C']),
                 random.randint(0, 1000))
            )
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Updating {num_updates} random users...")
        start = time.time()
        cur.execute(f"UPDATE users SET name = name || ' (updated)', updated_at = NOW() WHERE user_id IN (SELECT user_id FROM users ORDER BY RANDOM() LIMIT {num_updates})")
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Updating {num_updates} random orders...")
        start = time.time()
        cur.execute(f"UPDATE orders SET status = 'updated', updated_at = NOW() WHERE id IN (SELECT id FROM orders ORDER BY RANDOM() LIMIT {num_updates})")
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Updating {num_updates} random products...")
        start = time.time()
        cur.execute(f"UPDATE products SET price = price * 1.1, updated_at = NOW() WHERE product_id IN (SELECT product_id FROM products ORDER BY RANDOM() LIMIT {num_updates})")
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        print(f"  Updating {num_updates} random inventory...")
        start = time.time()
        cur.execute(f"UPDATE inventory SET quantity = quantity + 10, updated_at = NOW() WHERE inventory_id IN (SELECT inventory_id FROM inventory ORDER BY RANDOM() LIMIT {num_updates})")
        conn.commit()
        print(f"    Done in {time.time()-start:.2f}s")
        
        cur.close()
        conn.close()
    
    print("\n" + "=" * 70)
    total_changes = len(DATABASES) * (num_inserts * 5 + num_updates * 4)
    print(f"TOTAL CHANGES: {total_changes:,} rows across both databases")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    scale = sys.argv[1] if len(sys.argv) > 1 else "medium"
    
    scales = {
        "small": (500, 200),
        "medium": (2000, 1000),
        "large": (5000, 2000),
        "xlarge": (10000, 5000)
    }
    
    if scale in scales:
        generate_changes(*scales[scale])
    else:
        print(f"Usage: {sys.argv[0]} [small|medium|large|xlarge]")
