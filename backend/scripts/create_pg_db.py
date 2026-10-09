import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

conn = psycopg2.connect(host="localhost", port=5432, user="postgres", password="postgres", dbname="postgres")
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT 1 FROM pg_database WHERE datname = 'report_management'")
if cur.fetchone():
    print("Database 'report_management' already exists — skipping creation.")
else:
    cur.execute("CREATE DATABASE report_management")
    print("Database 'report_management' created successfully.")

cur.close()
conn.close()
