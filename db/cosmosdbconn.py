from azure.cosmos import CosmosClient, exceptions, PartitionKey


class CosmosDBConnection:
    def __init__(self, logger, endpoint: str, key: str, database_name: str, container_name: str):
        self.container = None
        self.client = None
        self.endpoint = endpoint
        self.key = key
        self.database_name = database_name
        self.container_name = container_name
        self.logger = logger

    def connect(self):
        try:
            self.client = CosmosClient(url=self.endpoint, credential=self.key)

            database = self.client.create_database_if_not_exists(id=self.database_name)

            self.container = database.create_container_if_not_exists(
                id=self.container_name,
                partition_key=PartitionKey(path="/correlation_id"),
                offer_throughput=400
            )
        except Exception as e:
            self.logger.error(e)
        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(e)

    def disconnect(self):
        pass

    def insert(self, item):
        try:
            self.container.upsert_item(body=item)
        except Exception as e:
            self.logger.error(e)
        except exceptions.CosmosAccessConditionFailedError as e:
            self.logger.error(e)
        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(e)
        except exceptions.CosmosClientTimeoutError as e:
            self.logger.error(e)

    def delete(self, id):
        self.container.delete_item(item=id)
