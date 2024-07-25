import websockets
import asyncio
import json

from dotenv import dotenv_values


async def send_and_receive(uri):
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Conectado a {uri}")

            # Enviar un mensaje al servidor
            event_data = {"CorrelationId": "ece34df4-4a4b-459c-a56c-54434aa878c1", "SessionData": None,
                          "Message": "Electric", "IsFinal": True, "Locale": "en-US"}
            await websocket.send(json.dumps(event_data))
            print(f"Mensaje enviado al servidor: {json.dumps(event_data)}")

            # Esperar la respuesta del servidor
            response = await websocket.recv()
            print(f"Respuesta recibida del servidor: {response}")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Conexión cerrada inesperadamente: {e}")

async def main():
    ENV_CONFIG = dotenv_values('env.test')
    await send_and_receive(ENV_CONFIG["DISA_WS_URI"])

if __name__ == "__main__":
    asyncio.run(main())
