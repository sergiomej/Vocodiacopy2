from mariadbconn import MariaDBConnection

db = MariaDBConnection(host="172.210.60.9", user='root', database='events', password="maria123")
db.connect()

# Example query to get MariaDB version
db.execute_query("SELECT VERSION();")
version = db.fetch_one()
if version:
    print(f"MariaDB version: {version[0]}")

db.close()