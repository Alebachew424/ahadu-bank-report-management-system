
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
conn = psycopg2.connect(host="localhost", port=5432, user="postgres", password="postgres", dbname="report_management")
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='requests' ORDER BY column_name")
for row in cur.fetchall():
    print(f"  {row[0]:<35} {row[1]}")
conn.close()
