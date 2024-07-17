from pyexpat import model
import uuid
from html import unescape
from urllib import request as request_lib, error
import sys
from urllib.parse import urlencode, urljoin
from azure.eventgrid import EventGridEvent, SystemEventNames
import requests
from flask import Flask, Response, request, json
from logging import INFO
import re
from azure.communication.callautomation import (
    CallAutomationClient,
    PhoneNumberIdentifier,
    RecognizeInputType,
    TextSource, FileSource
)

import logging
from logging.handlers import TimedRotatingFileHandler

import websockets
import asyncio

from azure.core.messaging import CloudEvent
import openai

from openai.api_resources import (
    ChatCompletion
)

# Your ACS resource connection string
ACS_CONNECTION_STRING = "endpoint=https://communication-disa-test.unitedstates.communication.azure.com/;accesskey=o4eO9kiaTeFSCGX1ka7h5HNbGdTqVQH0sFLSKQWblmtkW81zjn86JQQJ99AFACULyCphSYATAAAAAZCSFls1"

# Cognitive service endpoint
COGNITIVE_SERVICE_ENDPOINT = "https://testaivocodia.cognitiveservices.azure.com/"

# Cognitive service endpoint
AZURE_OPENAI_SERVICE_KEY = "<AZURE_OPENAI_SERVICE_KEY>"

# Open AI service endpoint
AZURE_OPENAI_SERVICE_ENDPOINT = "<AZURE_OPENAI_SERVICE_ENDPOINT>"

# Azure Open AI Deployment Model Name
AZURE_OPENAI_DEPLOYMENT_MODEL_NAME = "<AZURE_OPENAI_DEPLOYMENT_MODEL_NAME>"

# Azure Open AI Deployment Model
AZURE_OPENAI_DEPLOYMENT_MODEL = "gpt-3.5-turbo"

# Agent Phone Number
AGENT_PHONE_NUMBER = "+573044336760"

# Callback events URI to handle callback events.
CALLBACK_URI_HOST = "https://0343-172-208-55-190.ngrok-free.app"
CALLBACK_EVENTS_URI = CALLBACK_URI_HOST + "/api/callbacks"

ANSWER_PROMPT_SYSTEM_TEMPLATE = """ 
    You are an assistant designed to answer the customer query and analyze the sentiment score from the customer tone. 
    You also need to determine the intent of the customer query and classify it into categories such as sales, marketing, shopping, etc.
    Use a scale of 1-10 (10 being highest) to rate the sentiment score. 
    Use the below format, replacing the text in brackets with the result. Do not include the brackets in the output: 
    Content:[Answer the customer query briefly and clearly in two lines and ask if there is anything else you can help with] 
    Score:[Sentiment score of the customer tone] 
    Intent:[Determine the intent of the customer query] 
    Category:[Classify the intent into one of the categories]
    """

HELLO_PROMPT = "Hello, thank you for calling! How can I help you today?"
TIMEOUT_SILENCE_PROMPT = "I am sorry, I did not hear anything. If you need assistance, please let me know how I can help you,"
GOODBYE_PROMPT = "Thank you for calling! I hope I was able to assist you. Have a great day!"
CONNECT_AGENT_PROMPT = "I'm sorry, I was not able to assist you with your request. Let me transfer you to an agent who can help you further. Please hold the line, and I willl connect you shortly."
CALLTRANSFER_FAILURE_PROMPT = "It looks like I can not connect you to an agent right now, but we will get the next available agent to call you back as soon as possible."
AGENT_PHONE_NUMBER_EMPTY_PROMPT = "I am sorry, we are currently experiencing high call volumes and all of our agents are currently busy. Our next available agent will call you back as soon as possible."
END_CALL_PHRASE_TO_CONNECT_AGENT = "Sure, please stay on the line. I am going to transfer you to an agent."

TRANSFER_FAILED_CONTEXT = "TransferFailed"
CONNECT_AGENT_CONTEXT = "ConnectAgent"
GOODBYE_CONTEXT = "Goodbye"

CHAT_RESPONSE_EXTRACT_PATTERN = r"\s*Content:(.*)\s*Score:(.*\d+)\s*Intent:(.*)\s*Category:(.*)"

call_automation_client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)

recording_id = None
recording_chunks_location = []
max_retry = 2

openai.api_key = AZURE_OPENAI_SERVICE_KEY
openai.api_base = AZURE_OPENAI_SERVICE_ENDPOINT  # your endpoint should look like the following https://YOUR_RESOURCE_NAME.openai.azure.com/
openai.api_type = 'azure'
openai.api_version = '2023-05-15'  # this may change in the future

app = Flask(__name__)

correlation_id = ""

logging.basicConfig(
    filename='call.log',  # Nombre del archivo de logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Nivel de logging, por ejemplo DEBUG, INFO, ERROR
)


# Función para manejar la transferencia de llamada
def transfer_call_to_agent(call_connection_id):
    try:
        if not AGENT_PHONE_NUMBER or AGENT_PHONE_NUMBER.isspace():
            logging.info("Agent phone number is empty")
            handle_play(call_connection_id=call_connection_id, text_to_play=AGENT_PHONE_NUMBER_EMPTY_PROMPT)
        else:
            transfer_destination = PhoneNumberIdentifier(AGENT_PHONE_NUMBER)
            call_connection_client = call_automation_client.get_call_connection(call_connection_id=call_connection_id)
            call_connection_client.transfer_call_to_participant(target_participant=transfer_destination)
            logging.info("Transfer call initiated to agent")
    except Exception as ex:
        logging.error(f"Error transferring call to agent: {ex}")


def call_first_url():
    url = 'https://dfainbound.azurewebsites.net/api/v1/inbound/requestroute/3213215510/9546483989'  # Ejemplo de URL

    try:
        # Realizar la solicitud GET
        response = request_lib.urlopen(url)

        # Leer la respuesta
        data = json.loads(response.read().decode('utf-8'))

        # Imprimir la respuesta
        return data["Disa"]

    except error.URLError as e:
        print(f'Error al hacer la solicitud: {e}')


async def send_and_receive(uri, correlation_id, message):
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Conectado a {uri}")

            # Enviar un mensaje al servidor
            event_data = {"CorrelationId": correlation_id, "SessionData": None,
                          "Message": message, "IsFinal": True, "Locale": "en-US"}
            await websocket.send(json.dumps(event_data))
            print(f"Mensaje enviado al servidor: {json.dumps(event_data)}")

            # Esperar la respuesta del servidor
            response = await websocket.recv()
            print(f"Respuesta recibida del servidor: {response}")
            return response

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Conexión cerrada inesperadamente: {e}")


async def run_disa(correlation_id, message):
    uri = "wss://dwsspool.azurewebsites.net/dpm"  # Cambia esto por la URI de tu servidor WebSocket
    response = await send_and_receive(uri, correlation_id, message)
    return response


def get_chat_completions_async(system_prompt, user_prompt):
    openai.api_key = AZURE_OPENAI_SERVICE_KEY
    openai.api_base = AZURE_OPENAI_SERVICE_ENDPOINT  # your endpoint should look like the following https://YOUR_RESOURCE_NAME.openai.azure.com/
    openai.api_type = 'azure'
    openai.api_version = '2023-05-15'  # this may change in the future

    # Define your chat completions request
    chat_request = [
        {"role": "system", "content": f"{system_prompt}"},
        {"role": "user", "content": f"In less than 200 characters: respond to this question: {user_prompt}?"}
    ]

    global response_content
    try:
        response = ChatCompletion.create(model=AZURE_OPENAI_DEPLOYMENT_MODEL,
                                         deployment_id=AZURE_OPENAI_DEPLOYMENT_MODEL_NAME, messages=chat_request,
                                         max_tokens=1000)
    except Exception as ex:
        logging.info("error in openai api call : %s", ex)

    # Extract the response content
    if response is not None:
        response_content = response['choices'][0]['message']['content']
    else:
        response_content = ""
    return response_content


def get_chat_gpt_response(speech_input):
    return get_chat_completions_async(ANSWER_PROMPT_SYSTEM_TEMPLATE, speech_input)

def parse_url(html_string):
    # Decodifica entidades HTML a texto legible
    text = unescape(html_string)
    return text


def handle_recognize(replyText, callerId, call_connection_id, context="", url=""):
    # play_source = TextSource(text=replyText, voice_name="en-US-NancyNeural")

    # file = "https://audiopoctest.file.core.windows.net/audio/audiotest/6daf3d8c-d97d-4f19-bb6f-8e0789e0a5b4.wav?sv=2022-11-02&ss=bfqt&srt=sco&sp=rwdlacupiytfx&se=2024-07-16T00:00:19Z&st=2024-07-15T16:00:19Z&spr=https&sig=i0dlzFp2T6jZBDy0KEcClY4ScVg7WehUj7XWBep9TDM%3D"
    # file = url

    logging.info(f"URL to play: {url}")

    play_source = FileSource(url=url)

    recognize_result = call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier(callerId),
        end_silence_timeout=1,
        play_prompt=play_source,
        operation_context=context)
    """
    recognize_result = call_automation_client.get_call_connection(call_connection_id).play_media(
        play_source,
        operation_context=context)"""
    logging.info("handle_recognize : data=%s", recognize_result)


def handle_play(call_connection_id, url, context):
    logging.info(f"URL to play: {url}")

    play_source = FileSource(url=url)
    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(play_source,
                                                                                     operation_context=context)


def handle_hangup(call_connection_id):
    call_automation_client.get_call_connection(call_connection_id).hang_up(is_for_everyone=True)


def detect_escalate_to_agent_intent(speech_text, logger):
    return has_intent_async(user_query=speech_text, intent_description="talk to agent", logger=logger)


def has_intent_async(user_query, intent_description, logger):
    is_match = False
    system_prompt = "You are a helpful assistant"
    combined_prompt = f"In 1 word: does {user_query} have a similar meaning as {intent_description}?"
    # combined_prompt = base_user_prompt.format(user_query, intent_description)
    response = get_chat_completions_async(system_prompt, combined_prompt)
    if "yes" in response.lower():
        is_match = True
    logger.info(
        f"OpenAI results: is_match={is_match}, customer_query='{user_query}', intent_description='{intent_description}'")
    return is_match


def get_sentiment_score(sentiment_score):
    pattern = r"(\d)+"
    regex = re.compile(pattern)
    match = regex.search(sentiment_score)
    return int(match.group()) if match else -1


@app.route("/api/incomingCall", methods=['POST'])
def incoming_call_handler():
    for event_dict in request.json:
        event = EventGridEvent.from_dict(event_dict)
        logging.info("incoming event data --> %s", event.data)
        logging.info("incoming event data --> %s", event.data)
        if event.event_type == SystemEventNames.EventGridSubscriptionValidationEventName:
            logging.info("Validating subscription")
            validation_code = event.data['validationCode']
            validation_response = {'validationResponse': validation_code}
            return Response(response=json.dumps(validation_response), status=200)
        elif event.event_type == "Microsoft.Communication.IncomingCall":
            logging.info("Incoming call received: data=%s",
                         event.data)
            if event.data['from']['kind'] == "phoneNumber":
                caller_id = event.data['from']["phoneNumber"]["value"]
            else:
                caller_id = event.data['from']['rawId']
            logging.info("incoming call handler caller id: %s",
                         caller_id)
            incoming_call_context = event.data['incomingCallContext']
            guid = uuid.uuid4()
            query_parameters = urlencode({"callerId": caller_id})
            callback_uri = f"{CALLBACK_EVENTS_URI}/{guid}?{query_parameters}"

            logging.info("callback url: %s", callback_uri)

            answer_call_result = call_automation_client.answer_call(incoming_call_context=incoming_call_context,
                                                                    cognitive_services_endpoint=COGNITIVE_SERVICE_ENDPOINT,
                                                                    callback_url=callback_uri)
            logging.info("Answered call for connection id: %s",
                         answer_call_result.call_connection_id)
            return Response(status=200)


def iterate_response_actions(playback_assets: []):
    for asset in playback_assets:
        if asset['Action'] == 0:
            url_file = parse_url(asset["RecordingUrl"])
            handle_play(call_connection_id, url_file, "")
        elif asset['Action'] == 1:
            url_file = parse_url(asset["RecordingUrl"])
            handle_recognize(HELLO_PROMPT,
                             caller_id, call_connection_id,
                             context="GetFreeFormText", url=url_file)
        elif asset['Action'] == 21:
            url_file = parse_url(asset["RecordingUrl"])
            logging.info("Transfer to +++++++++++++++++++++++++++")
            transfer_call_to_agent(call_connection_id=call_connection_id)
        else:
            logging.info("No valid action")

@app.route("/api/callbacks/<contextId>", methods=["POST"])
def handle_callback(contextId):
    try:
        global caller_id, call_connection_id, correlation_id
        logging.info("Request Json: %s", request.json)
        for event_dict in request.json:
            event = CloudEvent.from_dict(event_dict)
            call_connection_id = event.data['callConnectionId']

            logging.info("%s event received for call connection id: %s", event.type, call_connection_id)
            caller_id = request.args.get("callerId").strip()
            if "+" not in caller_id:
                caller_id = "+".strip() + caller_id.strip()

            logging.info("call connected : data=%s", event.data)
            if event.type == "Microsoft.Communication.CallConnected":

                disa = call_first_url()

                logging.info(f"First url: {disa}")

                iterate_response_actions(disa["PlayBackAssets"])

                correlation_id = disa["CorrelationId"]

            elif event.type == "Microsoft.Communication.RecognizeCompleted":
                if event.data['recognitionType'] == "speech":
                    speech_text = event.data['speechResult']['speech']
                    logging.info("Recognition completed, speech_text =%s",
                                 speech_text)
                    if speech_text is not None and len(speech_text) > 0:
                        # if detect_escalate_to_agent_intent(speech_text=speech_text, logger=logging):
                        #    handle_play(call_connection_id=call_connection_id,
                        #                text_to_play=END_CALL_PHRASE_TO_CONNECT_AGENT, context=CONNECT_AGENT_CONTEXT)
                        # else:
                        res_question = "I am a response"

                        disa = asyncio.run(run_disa(correlation_id=correlation_id, message=speech_text))

                        disa = json.loads(disa)

                        correlation_id = disa["CorrelationId"]

                        iterate_response_actions(disa["PlayBackAssets"])

                        logging.info(f"Disa Respuesta recibida y almacenada en main(): {disa}")

                        # Poner aqui si recibe evento de transfer o el resto de logica
                        # logging.info("TRANSFERRRRRRRR+++++++++++++++++++++")
                        # transfer_call_to_agent(call_connection_id=call_connection_id)

                        handle_recognize(res_question, caller_id, call_connection_id,
                                         context="ResponseTest", url=disa)

                        """
                        chat_gpt_response = get_chat_gpt_response(speech_text)
                        logging.info(f"Chat GPT response:{chat_gpt_response}")
                        regex = re.compile(CHAT_RESPONSE_EXTRACT_PATTERN)
                        match = regex.search(chat_gpt_response)
                        if match:
                            answer = match.group(1)
                            sentiment_score = match.group(2).strip()
                            intent = match.group(3)
                            category = match.group(4)
                            logging.info(
                                f"Chat GPT Answer={answer}, Sentiment Rating={sentiment_score}, Intent={intent}, Category={category}")
                            score = get_sentiment_score(sentiment_score)
                            logging.info(f"Score={score}")
                            if -1 < score < 5:
                                logging.info(f"Score is less than 5")
                                handle_play(call_connection_id=call_connection_id,
                                            text_to_play=CONNECT_AGENT_PROMPT, context=CONNECT_AGENT_CONTEXT)
                            else:
                                logging.info(f"Score is more than 5")
                                handle_recognize(answer, caller_id, call_connection_id, context="OpenAISample")
                        else:
                            logging.info("No match found")
                            handle_recognize(chat_gpt_response, caller_id, call_connection_id,
                                             context="OpenAISample")
                        """

            elif event.type == "Microsoft.Communication.RecognizeFailed":

                resultInformation = event.data['resultInformation']
                reasonCode = resultInformation['subCode']
                context = event.data['operationContext']
                global max_retry
                if reasonCode == 8510 and 0 < max_retry:
                    handle_recognize(TIMEOUT_SILENCE_PROMPT, caller_id, call_connection_id)
                    max_retry -= 1
                else:
                    handle_play(call_connection_id, GOODBYE_PROMPT, GOODBYE_CONTEXT)

            elif event.type == "Microsoft.Communication.PlayCompleted":
                context = event.data['operationContext']

                if context.lower() == TRANSFER_FAILED_CONTEXT.lower() or context.lower() == GOODBYE_CONTEXT.lower():
                    handle_hangup(call_connection_id)
                elif context.lower() == CONNECT_AGENT_CONTEXT.lower():
                    if not AGENT_PHONE_NUMBER or AGENT_PHONE_NUMBER.isspace():
                        logging.info(f"Agent phone number is empty")
                        handle_play(call_connection_id=call_connection_id, text_to_play=AGENT_PHONE_NUMBER_EMPTY_PROMPT)
                    else:
                        logging.info(f"Initializing the Call transfer...")
                        transfer_destination = PhoneNumberIdentifier(AGENT_PHONE_NUMBER)
                        call_connection_client = call_automation_client.get_call_connection(
                            call_connection_id=call_connection_id)
                        call_connection_client.transfer_call_to_participant(target_participant=transfer_destination)
                        logging.info(f"Transfer call initiated: {context}")

            elif event.type == "Microsoft.Communication.CallTransferAccepted":
                logging.info(f"Call transfer accepted event received for connection id: {call_connection_id}")

            elif event.type == "Microsoft.Communication.CallTransferFailed":
                logging.info(f"Call transfer failed event received for connection id: {call_connection_id}")
                resultInformation = event.data['resultInformation']
                sub_code = resultInformation['subCode']
                # check for message extraction and code
                logging.info(f"Encountered error during call transfer, message=, code=, subCode={sub_code}")
                handle_play(call_connection_id=call_connection_id, text_to_play=CALLTRANSFER_FAILURE_PROMPT,
                            context=TRANSFER_FAILED_CONTEXT)
        return Response(status=200)
    except Exception as ex:
        logging.info(f"error in event handling [{ex}]")
        line = sys.exc_info()[-1].tb_lineno
        logging.error("Error in line #{} Msg: {}".format(line, ex))


@app.route("/")
def hello():
    return "Hello ACS CallAutomation!..test"


if __name__ == '__main__':
    correlation_id = ""
    app.run(port=8080)
