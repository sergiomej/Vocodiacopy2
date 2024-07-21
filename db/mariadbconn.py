import pymysql


class MariaDBConnection:
    """
    A class to manage a connection to a MariaDB database using PyMySQL.
    """

    def __init__(self, host, user, password, database):
        """
        Initializes the MariaDBConnection class with connection parameters.

        Args:
            host (str): The hostname or IP address of the MariaDB server.
            user (str): The username for the MariaDB connection.
            password (str): The password for the MariaDB connection.
            database (str): The name of the database to connect to.
        """
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        self.cursor = None

    def connect(self):
        """
        Establishes a connection to the MariaDB database and sets up the cursor.
        """
        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            self.cursor = self.connection.cursor()
            print("Connection established successfully.")
        except pymysql.MySQLError as e:
            print(f"Error connecting to MariaDB: {e}")

    def execute_query(self, query, params=None):
        """
        Executes a SQL query on the MariaDB database.

        Args:
            query (str): The SQL query to execute.
            params (tuple, optional): Parameters for the SQL query.
        """
        if self.cursor:
            try:
                self.cursor.execute(query, params)
                self.connection.commit()
                print("Query executed successfully.")
            except pymysql.MySQLError as e:
                print(f"Error executing query: {e}")

    def fetch_all(self):
        """
        Fetches all results from the last executed query.

        Returns:
            list: A list of tuples representing the rows of the query result.
        """
        if self.cursor:
            return self.cursor.fetchall()

    def fetch_one(self):
        """
        Fetches one result from the last executed query.

        Returns:
            tuple: A tuple representing a single row from the query result.
        """
        if self.cursor:
            return self.cursor.fetchone()

    def insert_event(self, correlation_id, phone, start, end, action, data, latency, label):
        """
        Inserts a new record into the 'event' table.

        Args:
            correlation_id (str): The correlation ID for the event.
            phone (str): The phone number associated with the event.
            start (datetime): The start datetime of the event.
            end (datetime): The end datetime of the event.
            action (str): The action performed in the event.
            data (bytes): The binary data related to the event.
            latency (int): The latency of the event.
            label (str): The label for the event.
        """
        query = """
          INSERT INTO event (correlation_id, phone, start, end, action, data, latency, label)
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
          """
        params = (
            correlation_id,  # CHAR(36)
            phone,  # VARCHAR(16)
            start,  # DATETIME(6)
            end,  # DATETIME(6)
            action,  # VARCHAR(12)
            data,  # TINYBLOB (binary data)
            latency,  # INT(11)
            label  # VARCHAR(32)
        )
        self.execute_query(query, params)

    def close(self):
        """
        Closes the connection to the MariaDB database and the cursor.
        """
        if self.connection:
            self.cursor.close()
            self.connection.close()
            print("Connection closed successfully.")
