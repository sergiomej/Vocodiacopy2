import websockets
import asyncio
import json


async def send_and_receive(uri):
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Conectado a {uri}")

            # Enviar un mensaje al servidor
            event_data = {"CorrelationId": "74929868-ff1f-46a9-b3dc-0a063d649c26", "SessionData": None,
                          "Message": "yes", "IsFinal": True, "Locale": "en-US"}
            await websocket.send(json.dumps(event_data))
            print(f"Mensaje enviado al servidor: {json.dumps(event_data)}")

            # Esperar la respuesta del servidor
            response = await websocket.recv()
            print(f"Respuesta recibida del servidor: {response}")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Conexión cerrada inesperadamente: {e}")

async def main():
    uri = "wss://dwsspool.azurewebsites.net/dpm"  # Cambia esto por la URI de tu servidor WebSocket
    await send_and_receive(uri)

if __name__ == "__main__":
    asyncio.run(main())