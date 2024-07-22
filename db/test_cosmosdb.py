from db.cosmosdbconn import CosmosDBConnection
from datetime import datetime
from db.events.call_event import CallEvent


def test_cosmosdb():
    dbcosmos = CosmosDBConnection(endpoint="https://milky-way-calling.documents.azure.com:443/",
                                  key="n07EmQti8ppFtoPTYzGxq9MIiV0mgYTiopfJxZneELrFWH5l891wO8CSlPyhSf45LIMO2ZusakjYACDbEv9elA==",
                                  database_name="switchdb_dev", container_name="call_events")

    call_event = CallEvent(correlation_id="111",
                           server_call_id="123",
                           phone="2222222",
                           action="disa",
                           data="1232313",
                           end_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           start_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    dbcosmos.connect()
    dbcosmos.insert(call_event.to_dict())
