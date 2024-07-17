from urllib import request, error
import json

def call_first_url():
    url = 'https://dfainbound.azurewebsites.net/api/v1/inbound/requestroute/3213215510/9546483989'  # Ejemplo de URL

    try:
        # Realizar la solicitud GET
        response = request.urlopen(url)

        # Leer la respuesta
        data = json.loads(response.read().decode('utf-8'))
        print(data["Disa"])
        # Imprimir la respuesta
        return data["Disa"]

    except error.URLError as e:
        print(f'Error al hacer la solicitud: {e}')

call_first_url()
