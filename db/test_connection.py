from mariadbconn import MariaDBConnection
from dotenv import dotenv_values
import datetime

ENV_CONFIG = dotenv_values('.env.test')
db = MariaDBConnection(
        host=ENV_CONFIG["MARIADB_HOST"],
        user=ENV_CONFIG["MARIADB_USER"],
        database=ENV_CONFIG["MARIADB_DATABASE"],
        password=ENV_CONFIG["MARIADB_PASS"],
        pool_size=1
)
db.connect()

# Example query to get MariaDB version
db.insert_event("1", "1", datetime.datetime.now(), datetime.datetime.now(), "1",
                "1".encode('utf-8'), 1, "1")

db.execute_query("SELECT VERSION();")
version = db.fetch_one()
if version:
    print(f"MariaDB version: {version[0]}")

db.close()
