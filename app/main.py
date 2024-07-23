import uuid
import sys
import logging
import asyncio

from threading import Thread
from urllib.parse import urlencode
from azure.eventgrid import EventGridEvent, SystemEventNames
from flask import Flask, Response, request, json
from util.disa_connection import DisaConnection
from util.action_processor import ActionProcessor
from db.cosmosdbconn import CosmosDBConnection
from db.events.call_event import CallEvent
from db.mariadbconn import MariaDBConnection

from azure.communication.callautomation import (
    AzureBlobContainerRecordingStorage,
    CallAutomationClient,
    PhoneNumberIdentifier,
    RecordingChannel,
    RecordingContent,
    RecordingFormat,
    RecordingProperties,
    ServerCallLocator
)

from azure.core.messaging import CloudEvent
from pymemcache.client.base import PooledClient
from util.logger_manager import LoggerManager

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

logger = LoggerManager(logger_name="switch_logger",
                       log_file="/var/log/call_log.log").handler()  # check call and import logging

cosmos_db = CosmosDBConnection(logger=logger, endpoint="https://milky-way-calling.documents.azure.com:443/",
                               key="n07EmQti8ppFtoPTYzGxq9MIiV0mgYTiopfJxZneELrFWH5l891wO8CSlPyhSf45LIMO2ZusakjYACDbEv9elA==",
                               database_name="switchdb_dev", container_name="call_events")

cosmos_db.connect()

# max_pool_size should be at least half the number of workers plus 1 and less than Max memcached connections - 1.
IN_MEM_STATE_CLIENT = PooledClient("127.0.0.1", max_pool_size=5)

# Database Client
# Pool size should be at least half of the number of workers plus 1 and less than Max DB connections - 1.
MARIADB_CLIENT = MariaDBConnection(
    host="172.210.60.9", user="root", database="events", password="maria123", pool_size=5
)
MARIADB_CLIENT.connect()


# This method is safe to called in a parallel thread because the MARIADB_CLIENT is using a connection pool
# that is safe-threaded.
def async_db_recording_status(
    azure_correlation_id: str,
    current_server_call_id: str,
    current_recording_id: str,
    disa_correlation_id: str,
    status: str,
) -> None:
    required_fields = "azure_correlation_id, server_call_id, recording_id, status"

    fields = required_fields
    value_holders = "%s, %s, %s, %s"
    base_params = (azure_correlation_id, current_server_call_id, current_recording_id, status)

    if disa_correlation_id:
        fields += ", disa_correlation_id"
        value_holders += ", %s"
        base_params = base_params + (
            disa_correlation_id,
            status,
        )
    else:
        base_params = base_params + (status,)

    SQL_QUERY = (
        f"INSERT INTO recordings({fields}) VALUES ({value_holders}) "
        "ON DUPLICATE KEY UPDATE status=%s"
    )

    logger.info("Inserting recording information into relational DB.")

    MARIADB_CLIENT.execute_query(SQL_QUERY, base_params)


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

                    logger.info(
                        f"Call connected. Starting recording for serverCallId {server_call_id}"
                    )

                    recording_response: RecordingProperties = (
                        call_automation_client.start_recording(
                            call_locator=ServerCallLocator(server_call_id),
                            recording_content_type=RecordingContent.Audio,
                            recording_channel_type=RecordingChannel.Unmixed,
                            recording_format_type=RecordingFormat.Wav,
                            recording_storage=AzureBlobContainerRecordingStorage(
                                container_url=blob_container_url
                            ),
                        )
                    )

                    logger.info(f"Started recording with ID: {recording_response.recording_id}")

                    # We keep a common state for all the recordings that are associated to a
                    # ServerCallId. This key, in theory, is unique per _phone call_.
                    IN_MEM_STATE_CLIENT.set(server_call_id, recording_response.recording_id)

                    disa = DisaConnection.call_first_url(
                        logger=logger, did=did, caller_id=caller_id
                    )

                    transfer_agent = disa.get("TransferDestination", "")
                    disa_correlation_id = disa.get("CorrelationId", "")
                    azure_correlation_id = event.data['correlationId']

                    logger.info(f"DISA correlation_id: {disa_correlation_id}")

                    # We push the tracking to a separate process. We don't need to wait for it
                    # to finish, hence the lack of `.join()` calls.
                    track_recording = Thread(
                        target=async_db_recording_status,
                        args=(
                            azure_correlation_id,
                            server_call_id,
                            recording_response.recording_id,
                            disa_correlation_id,
                            "started",
                        ),
                    )
                    track_recording.start()

                    action_proc = ActionProcessor(
                        logger=logger,
                        call_connection_id=call_connection_id,
                        caller_id=caller_id,
                        call_automation_client=call_automation_client,
                        transfer_agent=transfer_agent,
                        correlation_id=disa_correlation_id,
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
                    # The call was finished in a non expected manner.
                    server_call_id = event.data["serverCallId"]
                    azure_correlation_id = event.data["correlationId"]
                    recording_id_to_stop = IN_MEM_STATE_CLIENT.get(server_call_id).decode('utf-8')

                    if recording_id_to_stop:
                        logger.info(f"Call interrupted for serverCallId: {server_call_id}")
                        logger.info(f"Recording stopped automatically with ID: {recording_id_to_stop}")

                        IN_MEM_STATE_CLIENT.delete(server_call_id)

                        # We push the tracking to a separate process. We don't need to wait for it
                        # to finish, hence the lack of `.join()` calls.
                        track_recording = Thread(
                            target=async_db_recording_status,
                            args=(
                                azure_correlation_id,
                                server_call_id,
                                recording_id_to_stop,
                                None,
                                "disconnected",
                            ),
                        )
                        track_recording.start()
                    else:
                        logger.error(
                            (f"The call with serverCallId: {server_call_id} "
                             "does not have an associated recording id in memory.")
                        )

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
                    action = ""
                    logger.info(f"PlayCompleted: [{event.data}]")

                    context = event.data['operationContext']
                    part = context.split('/', 1)

                    if len(part) > 1:
                        correlation_id = part[0]
                        action = part[1]

                    if action == "50":
                        disa_response = asyncio.run(
                            DisaConnection.run_disa_socket(
                                correlation_id=correlation_id,
                                message="",
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
                    server_call_id = event.data["serverCallId"]
                    azure_correlation_id = event.data["correlationId"]
                    recording_id_to_stop = IN_MEM_STATE_CLIENT.get(server_call_id).decode('utf-8')

                    if recording_id_to_stop:
                        logger.info(
                            f"The call has ended. Stopping recording for serverCallId: {server_call_id}"
                        )

                        call_automation_client.stop_recording(
                            recording_id=recording_id_to_stop
                        )

                        logger.info(f"Stopped recording with ID: {recording_id_to_stop}")

                        IN_MEM_STATE_CLIENT.delete(server_call_id)

                        # We push the tracking to a separate process. We don't need to wait for it
                        # to finish, hence the lack of `.join()` calls.
                        track_recording = Thread(
                            target=async_db_recording_status,
                            args=(
                                azure_correlation_id,
                                server_call_id,
                                recording_response.recording_id,
                                None,
                                "stopped",
                            ),
                        )
                        track_recording.start()
                    else:
                        logger.error(
                            (f"The call with serverCallId: {server_call_id} "
                             "does not have an associated recording id in memory."
                             "maybe it was interrupted?")
                        )

                case "CallTransferFailed":
                    # A failure!
                    logger.error(
                        f"Call transfer failed event received for connection id: {call_connection_id}"
                    )
                    result_information = event.data["resultInformation"]
                    correlation_id = event.data["operationContext"]
                    sub_code = result_information["subCode"]
                    # check for message extraction and code
                    logger.error(
                        f"Encountered error during call transfer, message=, code=, subCode={sub_code}"
                    )

                    action_proc = ActionProcessor(
                        logger=logger,
                        call_connection_id=call_connection_id,
                        caller_id=caller_id,
                        call_automation_client=call_automation_client,
                        transfer_agent="",
                        correlation_id=correlation_id,
                    )

                    action_proc.handle_play_text(
                        call_connection_id=call_connection_id,
                        text="Transfer failed",
                        context=correlation_id
                    )

                    action_proc.handle_hangup()
                case "RecognizeFailed":
                    # User input couldn't be recognised.
                    result_info = event.data["resultInformation"]
                    reason_code = result_info["subCode"]
                    context = event.data["operationContext"]

                    action_proc = ActionProcessor(logger=logger, call_connection_id=call_connection_id,
                                                  call_automation_client=call_automation_client)

                    global max_retry

                    if reason_code == 8510 and 0 < max_retry:
                        action_proc.handle_recognize(caller_id, call_connection_id)
                        max_retry -= 1
                    else:
                        action_proc.handle_play(call_connection_id, GOODBYE_PROMPT)
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
        action_proc = ActionProcessor(logger=logger, call_connection_id=call_connection_id,
                                      call_automation_client=call_automation_client)
        action_proc.handle_hangup()
        return Response(status=500)


@app.route("/")
def hello():
    return "Hello ACS CallAutomation!..test"


if __name__ == '__main__':
    correlation_id = ""
    app.run(port=8080)
