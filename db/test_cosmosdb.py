from db.cosmosdbconn import CosmosDBConnection
from datetime import datetime
from db.events.call_event import CallEvent
from dotenv import dotenv_values

ENV_CONFIG = dotenv_values('env.test')


def test_cosmosdb():
    dbcosmos = CosmosDBConnection(
            endpoint=ENV_CONFIG["COSMOS_DB_ENDPOINT"]
            key=ENV_CONFIG["COSMOS_DB_KEY"],
            database_name=ENV_CONFIG["COSMOS_DB_DATABASE"],
            container_name=ENV_CONFIG["COSMOS_DB_CONTAINER"]
    )

    call_event = CallEvent(correlation_id="111",
                           server_call_id="123",
                           phone="2222222",
                           action="disa",
                           data="1232313",
                           end_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           start_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    dbcosmos.connect()
    dbcosmos.insert(call_event.to_dict())
