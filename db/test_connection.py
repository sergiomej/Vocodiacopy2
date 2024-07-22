from mariadbconn import MariaDBConnection
import datetime

db = MariaDBConnection(host="172.210.60.9", user='root', database='events', password="maria123", pool_size=1)
db.connect()

# Example query to get MariaDB version
db.insert_event("1", "1", datetime.datetime.now(), datetime.datetime.now(), "1",
                "1".encode('utf-8'), 1, "1")

db.execute_query("SELECT VERSION();")
version = db.fetch_one()
if version:
    print(f"MariaDB version: {version[0]}")

db.close()
