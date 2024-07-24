import json
import sys
import time
import asyncio
import uuid

from html import unescape
from urllib.parse import urlencode

from util.disa_connection import DisaConnection
from azure.communication.callautomation import (
    PhoneNumberIdentifier,
    RecognizeInputType,
    FileSource,
    CallAutomationClient,
    CommunicationIdentifier
)

COGNITIVE_SERVICE_ENDPOINT = "https://testaivocodia.cognitiveservices.azure.com/"
CALLBACK_URI_HOST = "https://switch.ngrok.dev"
CALLBACK_EVENTS_URI = CALLBACK_URI_HOST + "/api/callbacks"
ACS_CONNECTION_STRING = "endpoint=https://communication-disa-test.unitedstates.communication.azure.com/;accesskey=o4eO9kiaTeFSCGX1ka7h5HNbGdTqVQH0sFLSKQWblmtkW81zjn86JQQJ99AFACULyCphSYATAAAAAZCSFls1"


class ActionProcessor:

    def __init__(self, logger, call_connection_id, did=None, caller_id=None, call_automation_client=None,
                 transfer_agent="",
                 correlation_id=""):
        self.call_connection_id = call_connection_id
        self.logger = logger
        self.caller_id = caller_id
        self.did = did
        self.call_automation_client = call_automation_client
        self.transfer_agent = transfer_agent
        self.correlation_id = correlation_id

    def process(self, playback_assets):

        try:
            for asset in playback_assets:
                self.logger.info(f"Asset: {asset}")
                match asset['Action']:
                    case 0:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(self.call_connection_id, url_file, context=self.correlation_id)
                        time.sleep(duration / 1000.0)
                    case 1:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        self.handle_recognize(
                            self.caller_id, self.call_connection_id,
                            context=self.correlation_id, url=url_file)
                    case 2:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(self.call_connection_id, url_file, context=self.correlation_id)
                        time.sleep(duration / 1000.0)
                        self.transfer_call_to_agent(call_connection_id=self.call_connection_id,
                                                    agent_phone_number=self.transfer_agent)
                    case 20:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(self.call_connection_id, url_file, context=self.correlation_id)
                        time.sleep(duration / 1000.0)
                        self.warm_transfer(call_connection_id=self.call_connection_id,
                                           agent_phone_number=self.transfer_agent)
                    case 50:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(self.call_connection_id, url_file, context=self.correlation_id, action="50")
                        time.sleep(duration / 1000.0)
                    case _:
                        self.logger.info(f"No valid action [{asset}]")
        except Exception as e:
            self.logger.error(e)
            line = sys.exc_info()[-1].tb_lineno
            self.logger.error("Error in line #{} Msg: {}".format(line, e))
            self.handle_hangup()

    def handle_recognize(self, callerId, call_connection_id, context="", url=""):
        self.logger.info(f"URL to play: {url}")

        play_source = FileSource(url=url)

        recognize_result = self.call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier(callerId),
            end_silence_timeout=1.5,
            play_prompt=play_source,
            interrupt_prompt=True,
            operation_context=context)

        self.logger.info("handle_recognize : data=%s", recognize_result)

    def handle_play(self, call_connection_id, url=None, context=None, action=None):
        self.logger.info(f"URL to play: {url}")
        self.logger.info(f"Action: {action}")

        if action == "50":
            operation_context = f"{context}/{action}"
        else:
            operation_context = context

        play_to = PhoneNumberIdentifier(self.caller_id)

        play_source = FileSource(url=url)
        self.call_automation_client.get_call_connection(call_connection_id).play_media_to_all(play_source,
                                                                                              operation_context=operation_context)

    def handle_hangup(self):
        self.call_automation_client.get_call_connection(self.call_connection_id).hang_up(is_for_everyone=True)

    def transfer_call_to_agent(self, call_connection_id, agent_phone_number):
        try:
            if not agent_phone_number or agent_phone_number.isspace():
                self.logger.info("Agent phone number is empty")
                self.handle_play(call_connection_id=call_connection_id, text_to_play="No agent to transfer")
            else:
                transfer_destination = PhoneNumberIdentifier(agent_phone_number)
                call_connection_client = self.call_automation_client.get_call_connection(
                    call_connection_id=call_connection_id)
                call_connection_client.transfer_call_to_participant(target_participant=transfer_destination,
                                                                    operation_context=self.correlation_id)
                self.logger.info(f"Transfer call initiated to agent {agent_phone_number}")
        except Exception as ex:
            self.logger.error(f"Error transferring call to agent: {ex}")

    def warm_transfer(self, call_connection_id, agent_phone_number):
        try:
            # call_automation_client_p = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
            transfer_destination = PhoneNumberIdentifier(agent_phone_number)
            source = PhoneNumberIdentifier(self.did)

            self.logger.info(f"Caller phone number: {self.caller_id}")
            self.logger.info(f"DID phone number: {self.did}")

            guid = uuid.uuid4()
            query_parameters = urlencode({"callerId": self.caller_id, "did": self.did})
            callback_uri = f"{CALLBACK_EVENTS_URI}/{guid}?{query_parameters}"

            operation_context = {
                "first_call": False,
                "caller_id": self.caller_id,
                "call_connection_id": call_connection_id
            }

            self.call_automation_client.get_call_connection(call_connection_id).add_participant(
                source_caller_id_number=source,
                target_participant=transfer_destination,
                operation_context=json.dumps(
                    operation_context))

            self.logger.info(f"Warm transfer call initiated to agent {self.call_automation_client}")

        except Exception as ex:
            self.logger.error(f"Error transferring call to agent: {ex}")

    @staticmethod
    def parse_url(html_string):
        # Decode html to text
        text = unescape(html_string)
        return text
