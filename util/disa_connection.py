import json
import websockets
from urllib import request, error


class DisaConnection:

    def __init__(self):
        pass

    @staticmethod
    def call_first_url(did, caller_id):

        if did.startswith('+'):
            did = did[1:]
        if caller_id.startswith('+'):
            caller_id = caller_id[1:]

        url = f"https://dfainbound.azurewebsites.net/api/v1/inbound/requestroute/{did}/{caller_id}"

        try:
            response = request.urlopen(url)
            data = json.loads(response.read().decode('utf-8'))
            print(f'Response first url: {data["Disa"]}')
            return data["Disa"]

        except error.URLError as e:
            print(f'Error getting the first url [{url}]: {e}')

    @staticmethod
    async def run_disa_socket(correlation_id, message):
        uri = "wss://dwsspool.azurewebsites.net/dpm"  # Cambia esto por la URI de tu servidor WebSocket
        response = await DisaConnection.send_and_receive(uri, correlation_id, message)
        return response

    @staticmethod
    async def send_and_receive(uri, correlation_id, message):
        try:
            async with websockets.connect(uri) as websocket:
                print(f"Connected to {uri}")

                # Send msg to socket
                event_data = {"CorrelationId": correlation_id, "SessionData": None,
                              "Message": message, "IsFinal": True, "Locale": "en-US"}
                await websocket.send(json.dumps(event_data))
                print(f"Message sent to disa: {json.dumps(event_data)}")

                # Wait for the server response
                response = await websocket.recv()
                print(f"Response from disa socket: {response}")
                return response

        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection close error: {e}")
