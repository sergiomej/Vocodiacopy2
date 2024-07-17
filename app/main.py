import uuid
import sys
import logging
import asyncio

from urllib.parse import urlencode
from azure.eventgrid import EventGridEvent, SystemEventNames
from flask import Flask, Response, request, json
from util.disa_connection import DisaConnection
from util.action_processor import ActionProcessor

from azure.communication.callautomation import (
    CallAutomationClient,
    PhoneNumberIdentifier
)

from azure.core.messaging import CloudEvent

# Your ACS resource connection string
ACS_CONNECTION_STRING = "endpoint=https://communication-disa-test.unitedstates.communication.azure.com/;accesskey=o4eO9kiaTeFSCGX1ka7h5HNbGdTqVQH0sFLSKQWblmtkW81zjn86JQQJ99AFACULyCphSYATAAAAAZCSFls1"

# Cognitive service endpoint
COGNITIVE_SERVICE_ENDPOINT = "https://testaivocodia.cognitiveservices.azure.com/"

# Callback events URI to handle callback events.
CALLBACK_URI_HOST = "https://switch.ngrok.dev"
CALLBACK_EVENTS_URI = CALLBACK_URI_HOST + "/api/callbacks"

GOODBYE_PROMPT = "Thank you for calling! I hope I was able to assist you. Have a great day!"
CONNECT_AGENT_PROMPT = "I'm sorry, I was not able to assist you with your request. Let me transfer you to an agent who can help you further. Please hold the line, and I willl connect you shortly."

#TRANSFER_FAILED_CONTEXT = "TransferFailed"
#CONNECT_AGENT_CONTEXT = "ConnectAgent"
#GOODBYE_CONTEXT = "Goodbye"

#AGENT_PHONE_NUMBER_EMPTY_PROMPT = "I am sorry, we are currently experiencing high call volumes and all of our agents are currently busy. Our next available agent will call you back as soon as possible."

call_automation_client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)

recording_id = None
recording_chunks_location = []
max_retry = 2

app = Flask(__name__)

correlation_id = ""

logging.basicConfig(
    filename='call.log',  # Nombre del archivo de logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Nivel de logging, por ejemplo DEBUG, INFO, ERROR
)


@app.route("/api/incomingCall", methods=['POST'])
def incoming_call_handler():
    for event_dict in request.json:
        event = EventGridEvent.from_dict(event_dict)
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

            if event.data['to']['kind'] == "phoneNumber":
                did = event.data['to']["phoneNumber"]["value"]
            else:
                did = event.data['to']['rawId']

            logging.info("incoming call handler caller id: %s",
                         caller_id)

            logging.info("incoming call handler did: %s",
                         did)

            incoming_call_context = event.data['incomingCallContext']
            guid = uuid.uuid4()
            query_parameters = urlencode({"callerId": caller_id, "did": did})
            callback_uri = f"{CALLBACK_EVENTS_URI}/{guid}?{query_parameters}"

            logging.info("callback url: %s", callback_uri)

            answer_call_result = call_automation_client.answer_call(incoming_call_context=incoming_call_context,
                                                                    cognitive_services_endpoint=COGNITIVE_SERVICE_ENDPOINT,
                                                                    callback_url=callback_uri)
            logging.info("Answered call for connection id: %s",
                         answer_call_result.call_connection_id)
            return Response(status=200)


@app.route("/api/callbacks/<contextId>", methods=["POST"])
def handle_callback(contextId):
    try:
        global did, caller_id, call_connection_id, correlation_id, transfer_agent
        logging.info("Request Json: %s", request.json)
        for event_dict in request.json:
            event = CloudEvent.from_dict(event_dict)
            call_connection_id = event.data['callConnectionId']

            logging.info("%s event received for call connection id: %s", event.type, call_connection_id)
            caller_id = request.args.get("callerId").strip()
            did = request.args.get("did").strip()

            if "+" not in caller_id:
                caller_id = "+".strip() + caller_id.strip()

            if "+" not in did:
                did = "+".strip() + did.strip()

            logging.info("call connected : data=%s", event.data)
            if event.type == "Microsoft.Communication.CallConnected":

                disa = DisaConnection.call_first_url(did=did, caller_id=caller_id)

                transfer_agent = disa.get("TransferDestination", "")
                correlation_id = disa.get("CorrelationId", "")

                action_proc = ActionProcessor(logger=logging, call_connection_id=call_connection_id,
                                              caller_id=caller_id, call_automation_client=call_automation_client,
                                              transfer_agent=transfer_agent, correlation_id=correlation_id)
                action_proc.process(disa["PlayBackAssets"])

            elif event.type == "Microsoft.Communication.RecognizeCompleted":
                if event.data['recognitionType'] == "speech":
                    speech_text = event.data['speechResult']['speech']
                    logging.info("Recognition completed, speech_text =%s",
                                 speech_text)
                    if speech_text is not None and len(speech_text) > 0:

                        disa_response = asyncio.run(DisaConnection.run_disa_socket(correlation_id=correlation_id,
                                                                                   message=speech_text))

                        disa_response = json.loads(disa_response)

                        logging.info(f"Response from disa: {disa_response}")

                        correlation_id = disa_response["CorrelationId"]

                        action_proc = ActionProcessor(logger=logging, call_connection_id=call_connection_id,
                                                      caller_id=caller_id,
                                                      call_automation_client=call_automation_client,
                                                      transfer_agent=transfer_agent, correlation_id=correlation_id)
                        action_proc.process(disa_response["PlayBackAssets"])

            elif event.type == "Microsoft.Communication.RecognizeFailed":
                result_info = event.data['resultInformation']
                reason_code = result_info['subCode']
                context = event.data['operationContext']
                global max_retry
                if reason_code == 8510 and 0 < max_retry:
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
