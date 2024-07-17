from urllib.parse import urlparse

url = "https://demasrec.file.core.windows.net/audiosmb/devteam/69d467ca-6500-4173-ba1e-c409631e95fb/design/a7d53d73-79e6-42d7-823c-0a633eeca51f.wav?sv=2024-05-04&amp;se=2034-06-01T20%3A21%3A35Z&amp;sr=f&amp;sp=r&amp;sig=qhzLwSLPXck9yXKdrwiOgPsvkw98KoVjHuW10Q8Av1A%3D"


def parse_url(url):
    parsed_url = urlparse(url)

    path = parsed_url.path

    start_index = path.find('/audiosmb')

    end_index = path.find('.wav')

    if start_index != -1 and end_index != -1:
        result = path[start_index:end_index]
        print(result)
    else:
        print("Not found segment /audiosmb or .wav in the URL")

parse_url(url)

from html import unescape

def html_to_text(html_string):
    # Decodifica entidades HTML a texto legible
    text = unescape(html_string)
    return text

# Ejemplo de uso
text = html_to_text(url)
print(text)