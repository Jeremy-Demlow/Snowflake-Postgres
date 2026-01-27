#!/usr/bin/env python
"""
Fast batch data generation using execute_values for bulk inserts.

Usage:
    python scripts/fast_data_gen.py --host your-host.com --user admin small
    python scripts/fast_data_gen.py --host your-host.com large
    
    # Or with environment variables:
    PG_HOST=your-host.com PG_PASSWORD=xxx python scripts/fast_data_gen.py large

Password must be provided via PG_PASSWORD environment variable (never on CLI).
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

DATABASES = ['customer_a_db', 'customer_b_db']
SCALES = {
    "small": (500, 200),
    "medium": (2000, 1000), 
    "large": (5000, 2000), 
    "xlarge": (10000, 5000)
}


def get_conn(host, user, password, db):
    return psycopg2.connect(host=host, port=5432, database=db, user=user, password=password)


def generate_changes(host, user, password, num_inserts=1000, num_updates=500):
    print("=" * 70)
    print(f"GENERATING TEST DATA (BATCH MODE)")
    print(f"  Host: {host}")
    print(f"  INSERTs: {num_inserts} per table, UPDATEs: {num_updates} per table")
    print("=" * 70)
    
    now = datetime.now()
    
    for db in DATABASES:
        print(f"\n[{db}]")
        conn = get_conn(host, user, password, db)
        cur = conn.cursor()
        
        cur.execute("SELECT COALESCE(MAX(user_id),0) FROM users")
        max_user = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(id),0) FROM orders")
        max_order = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(payment_id),0) FROM payments")
        max_payment = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(product_id),0) FROM products")
        max_product = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(inventory_id),0) FROM inventory")
        max_inv = cur.fetchone()[0]
        print(f"  Max IDs: users={max_user}, orders={max_order}, payments={max_payment}, products={max_product}, inv={max_inv}")
        
        print(f"  Users...", end=" ", flush=True)
        start = time.time()
        data = [(max_user + i + 1, f'User{max_user+i+1}', f'u{max_user+i+1}@t.co', now, now) for i in range(num_inserts)]
        execute_values(cur, "INSERT INTO users (user_id, name, email, created_at, updated_at) VALUES %s", data)
        conn.commit()
        print(f"{time.time()-start:.1f}s")
        
        print(f"  Orders...", end=" ", flush=True)
        start = time.time()
        data = [(max_order + i + 1, random.randint(1, max_user), round(random.uniform(10, 500), 2), 
                random.choice(['pending', 'done', 'ship']), now, now, now) for i in range(num_inserts)]
        execute_values(cur, "INSERT INTO orders (id, user_id, amount, status, order_date, created_at, updated_at) VALUES %s", data)
        conn.commit()
        print(f"{time.time()-start:.1f}s")
        
        print(f"  Payments...", end=" ", flush=True)
        start = time.time()
        data = [(max_payment + i + 1, random.randint(1, max_order), round(random.uniform(10, 500), 2),
                random.choice(['card', 'paypal', 'bank']), random.choice(['ok', 'fail']), now, now, now) for i in range(num_inserts)]
        execute_values(cur, "INSERT INTO payments (payment_id, order_id, amount, method, status, processed_at, created_at, updated_at) VALUES %s", data)
        conn.commit()
        print(f"{time.time()-start:.1f}s")
        
        print(f"  Products...", end=" ", flush=True)
        start = time.time()
        data = [(max_product + i + 1, f'Prod{max_product+i+1}', f'Desc{i}', round(random.uniform(5, 200), 2),
                random.choice(['elec', 'cloth', 'home']), random.randint(0, 1000), now, now) for i in range(num_inserts)]
        execute_values(cur, "INSERT INTO products (product_id, name, description, price, category, stock_quantity, created_at, updated_at) VALUES %s", data)
        conn.commit()
        print(f"{time.time()-start:.1f}s")
        
        print(f"  Inventory...", end=" ", flush=True)
        start = time.time()
        data = [(max_inv + i + 1, random.randint(1, max_product), random.choice(['A', 'B', 'C']), 
                random.randint(0, 1000), now, now, now) for i in range(num_inserts)]
        execute_values(cur, "INSERT INTO inventory (inventory_id, product_id, warehouse_code, quantity, last_restocked, created_at, updated_at) VALUES %s", data)
        conn.commit()
        print(f"{time.time()-start:.1f}s")
        
        print(f"  Updates...", end=" ", flush=True)
        start = time.time()
        cur.execute(f"UPDATE users SET name = name || '*', updated_at = NOW() WHERE user_id IN (SELECT user_id FROM users ORDER BY RANDOM() LIMIT {num_updates})")
        cur.execute(f"UPDATE orders SET status = 'upd', updated_at = NOW() WHERE id IN (SELECT id FROM orders ORDER BY RANDOM() LIMIT {num_updates})")
        cur.execute(f"UPDATE products SET price = price * 1.05, updated_at = NOW() WHERE product_id IN (SELECT product_id FROM products ORDER BY RANDOM() LIMIT {num_updates})")
        cur.execute(f"UPDATE inventory SET quantity = quantity + 5, updated_at = NOW() WHERE inventory_id IN (SELECT inventory_id FROM inventory ORDER BY RANDOM() LIMIT {num_updates})")
        conn.commit()
        print(f"{time.time()-start:.1f}s")
        
        cur.close()
        conn.close()
    
    total = len(DATABASES) * (num_inserts * 5 + num_updates * 4)
    print(f"\nTOTAL: {total:,} changes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate test data for CDC replication testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/fast_data_gen.py --host mydb.example.com small
  python scripts/fast_data_gen.py --host mydb.example.com --user admin large
  PG_PASSWORD=xxx python scripts/fast_data_gen.py --host mydb.example.com xlarge

Scales:
  small   -  500 inserts,  200 updates per table
  medium  - 2000 inserts, 1000 updates per table
  large   - 5000 inserts, 2000 updates per table
  xlarge  - 10000 inserts, 5000 updates per table
"""
    )
    parser.add_argument("--host", default=os.environ.get("PG_HOST"), 
                        help="Postgres host (or set PG_HOST env var)")
    parser.add_argument("--user", default=os.environ.get("PG_USER", "snowflake_admin"),
                        help="Postgres user (default: snowflake_admin)")
    parser.add_argument("scale", nargs="?", default="large", choices=SCALES.keys(),
                        help="Data scale: small, medium, large, xlarge (default: large)")
    
    args = parser.parse_args()
    
    password = os.environ.get("PG_PASSWORD")
    if not password:
        print("Error: PG_PASSWORD environment variable required", file=sys.stderr)
        sys.exit(1)
    if not args.host:
        print("Error: --host required or set PG_HOST environment variable", file=sys.stderr)
        sys.exit(1)
    
    num_inserts, num_updates = SCALES[args.scale]
    generate_changes(args.host, args.user, password, num_inserts, num_updates)
