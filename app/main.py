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
    AzureBlobContainerRecordingStorage,
    CallAutomationClient,
    PhoneNumberIdentifier,
    RecordingChannel,
    RecordingContent,
    RecordingFormat,
    RecordingProperties
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

# TRANSFER_FAILED_CONTEXT = "TransferFailed"
# CONNECT_AGENT_CONTEXT = "ConnectAgent"
# GOODBYE_CONTEXT = "Goodbye"

# AGENT_PHONE_NUMBER_EMPTY_PROMPT = "I am sorry, we are currently experiencing high call volumes and all of our agents are currently busy. Our next available agent will call you back as soon as possible."

call_automation_client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)

recording_id = None
recording_chunks_location = []
max_retry = 2

app = Flask(__name__)

correlation_id = ""

logger = logging.getLogger('mi_logger')
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
stream_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler('call_log.log')
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# TODO: Maybe something like memcached or redict ?
IN_MEM_STATE = dict()

@app.route("/api/incomingCall", methods=['POST'])
def incoming_call_handler():
    for event_dict in request.json:
        event = EventGridEvent.from_dict(event_dict)
        logger.info("incoming event data --> %s", event.data)
        if event.event_type == SystemEventNames.EventGridSubscriptionValidationEventName:
            logger.info("Validating subscription")
            validation_code = event.data['validationCode']
            validation_response = {'validationResponse': validation_code}
            return Response(response=json.dumps(validation_response), status=200)
        elif event.event_type == "Microsoft.Communication.IncomingCall":
            logger.info("Incoming call received: data=%s",
                         event.data)

            if event.data['from']['kind'] == "phoneNumber":
                caller_id = event.data['from']["phoneNumber"]["value"]
            else:
                caller_id = event.data['from']['rawId']

            logger.info("incoming call handler caller id: %s",
                         caller_id)

            if event.data['to']['kind'] == "phoneNumber":
                did = event.data['to']["phoneNumber"]["value"]
            else:
                did = event.data['to']['rawId']

            logger.info("incoming call handler caller id: %s",
                         caller_id)

            logger.info("incoming call handler did: %s",
                         did)

            incoming_call_context = event.data['incomingCallContext']
            guid = uuid.uuid4()
            query_parameters = urlencode({"callerId": caller_id, "did": did})
            callback_uri = f"{CALLBACK_EVENTS_URI}/{guid}?{query_parameters}"

            logger.info("callback url: %s", callback_uri)

            answer_call_result = call_automation_client.answer_call(incoming_call_context=incoming_call_context,
                                                                    cognitive_services_endpoint=COGNITIVE_SERVICE_ENDPOINT,
                                                                    callback_url=callback_uri)
            logger.info("Answered call for connection id: %s",
                         answer_call_result.call_connection_id)
            return Response(status=200)


@app.route("/api/callbacks/<contextId>", methods=["POST"])
def handle_callback(contextId):
    try:
        global did, caller_id, call_connection_id, correlation_id, transfer_agent
        logger.info("Request Json: %s", request.json)
        for event_dict in request.json:
            event = CloudEvent.from_dict(event_dict)
            call_connection_id = event.data["callConnectionId"]

            logger.info(
                "%s event received for call connection id: %s", event.type, call_connection_id
            )
            caller_id = request.args.get("callerId").strip()
            did = request.args.get("did").strip()

            if "+" not in caller_id:
                caller_id = "+".strip() + caller_id.strip()

            if "+" not in did:
                did = "+".strip() + did.strip()

            logger.info("call connected : data=%s", event.data)

            communication_event_type = event.type.split("Microsoft.Communication.").pop()

            server_call_id = event.data["serverCallId"]  # Mandatory for recording
            # TODO: Extract to ENV
            blob_container_url = "https://audiopoctest.blob.core.windows.net/audiorecordings"

            match communication_event_type:
                case "CallConnected":
                    # Call connected

                    recording_response: RecordingProperties = (
                        call_automation_client.start_recording(
                            call_locator=server_call_id,
                            recording_content_type=RecordingContentType.Audio,
                            recording_channel_type=RecordingChannel.Unmixed,
                            recording_format_type=RecordingFormat.Wav,
                            recording_storage=AzureBlobContainerRecordingStorage(
                                container_url=blob_container_url
                            ),
                        )
                    )

                    # We keep a common state for all the recordings that are associated to a
                    # ServerCallId. This key, in theory, is unique per _phone call_.
                    IN_MEM_STATE[server_call_id] = recording_response

                    disa = DisaConnection.call_first_url(
                            logger=logger, did=did, caller_id=caller_id
                        )

                    transfer_agent = disa.get("TransferDestination", "")
                    correlation_id = disa.get("CorrelationId", "")

                    logger.info(f"primer correlation_id: {correlation_id}")

                    action_proc = ActionProcessor(
                        logger=logger,
                        call_connection_id=call_connection_id,
                        caller_id=caller_id,
                        call_automation_client=call_automation_client,
                        transfer_agent=transfer_agent,
                        correlation_id=correlation_id,
                    )

                    action_proc.process(disa["PlayBackAssets"])
                case "CallTransferAccepted":
                    # Call transfered to another endpoint
                    logging.info(
                        f"Call transfer accepted event received for connection id: {call_connection_id}"
                    )
                case "RecognizeCompleted":
                    # User input received correctly
                    # We assume, for the time being, that we only handle speech to text.
                    # Options for recognition types: speech | dtmf | choices | speechordtmf
                    if event.data["recognitionType"] == "speech":
                        speech_text = event.data["speechResult"]["speech"]

                        logger.info("Recognition completed, speech_text =%s", speech_text)

                        if speech_text is not None and len(speech_text) > 0:
                            logger.info(
                                f"Data to send DISA socket: correlation_id={event.data['operationContext']}, message={speech_text}"
                            )

                            disa_response = asyncio.run(
                                DisaConnection.run_disa_socket(
                                    correlation_id=event.data["operationContext"],
                                    message=speech_text,
                                )
                            )

                            disa_response = json.loads(disa_response)

                            logger.info(f"Response from disa: {disa_response}")

                            correlation_id = disa_response["CorrelationId"]

                            action_proc = ActionProcessor(
                                logger=logging,
                                call_connection_id=call_connection_id,
                                caller_id=caller_id,
                                call_automation_client=call_automation_client,
                                transfer_agent="",
                                correlation_id=correlation_id,
                            )
                            action_proc.process(disa_response["PlayBackAssets"])
                        else:
                            logger.error(f"Something looks weird. No speech detected. {event.data}")
                            # Speech text didn't work???
                case "CallDisconnected":
                    # Call disconnected
                    continue
                case "AddParticipantSucceeded":
                    # Added participant to call - This is triggered when bot answer succeeded.
                    continue
                case "CancelAddParticipantSucceeded":
                    # Cancelled an addition
                    continue
                case "RemoveParticipantSucceeded":
                    # Participant removed from call
                    continue
                case "ParticipantsUpdated":
                    # a participant status changed while call leg was connected to call
                    continue
                case "PlayCompleted":
                    # Audio provided to call played correctly
                    continue

                    # TODO: Be creative!
                    # context = event.data['operationContext']
                    # if context.lower() == TRANSFER_FAILED_CONTEXT.lower() or context.lower() == GOODBYE_CONTEXT.lower():
                    #     handle_hangup(call_connection_id)
                    # # Accepted
                    # elif context.lower() == CONNECT_AGENT_CONTEXT.lower():
                    #     if not AGENT_PHONE_NUMBER or AGENT_PHONE_NUMBER.isspace():
                    #         logger.info(f"Agent phone number is empty")
                    #         handle_play(call_connection_id=call_connection_id, text_to_play=AGENT_PHONE_NUMBER_EMPTY_PROMPT)
                    #     else:
                    #         logger.info(f"Initializing the Call transfer...")
                    #         transfer_destination = PhoneNumberIdentifier(AGENT_PHONE_NUMBER)
                    #         call_connection_client = call_automation_client.get_call_connection(
                    #             call_connection_id=call_connection_id)
                    #         call_connection_client.transfer_call_to_participant(target_participant=transfer_destination)
                    #         logger.info(f"Transfer call initiated: {context}")
                case "PlayCanceled":
                    # Request to cancel a play worked
                    continue
                case "RecognizeCanceled":
                    # A request to cancel an input received.
                    continue
                case "RecordingStateChanged":
                    # Status of recording action has been toggle (active | inactive)
                    continue
                case "CallEnded":
                    # The call has finished
                    continue
                case "CallTransferFailed":
                    # A failure!
                    logger.error(
                        f"Call transfer failed event received for connection id: {call_connection_id}"
                    )
                    resultInformation = event.data["resultInformation"]
                    sub_code = resultInformation["subCode"]
                    # check for message extraction and code
                    logger.error(
                        f"Encountered error during call transfer, message=, code=, subCode={sub_code}"
                    )
                    handle_play(
                        call_connection_id=call_connection_id,
                        text_to_play=CALLTRANSFER_FAILURE_PROMPT,
                        context=TRANSFER_FAILED_CONTEXT,
                    )
                case "RecognizeFailed":
                    # User input couldn't be recognised.
                    result_info = event.data["resultInformation"]
                    reason_code = result_info["subCode"]
                    context = event.data["operationContext"]

                    global max_retry

                    # Waiting for answer reached timeout, so we check if we can retry
                    # more reason codes: https://learn.microsoft.com/en-us/azure/communication-services/how-tos/call-automation/recognize-action?pivots=programming-language-python#event-codes
                    if reason_code == 8510 and 0 < max_retry:
                        handle_recognize(TIMEOUT_SILENCE_PROMPT, caller_id, call_connection_id)
                        max_retry -= 1
                    else:
                        handle_play(call_connection_id, GOODBYE_PROMPT, GOODBYE_CONTEXT)
                case "AddParticipanFailed":
                    # Added participant failed!
                    continue
                case "CancelAddParticipantFailed":
                    # A failure!
                    continue
                case "RemoveParticipantFailed":
                    # A failure!
                    continue
                case "PlayFailed":
                    # An error playing the audio!
                    continue
                case _:
                    # Default
                    continue

        # We should always return a 200 OK when an object has been handled correctly
        return Response(status=200)
    except Exception as ex:
        logger.info(f"error in event handling [{ex}]")
        line = sys.exc_info()[-1].tb_lineno
        logger.error("Error in line #{} Msg: {}".format(line, ex))
        return Response(status=500)


@app.route("/")
def hello():
    return "Hello ACS CallAutomation!..test"


if __name__ == '__main__':
    correlation_id = ""
    app.run(port=8080)
