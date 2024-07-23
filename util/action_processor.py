import sys
import time
import asyncio

from html import unescape
from util.disa_connection import DisaConnection
from azure.communication.callautomation import (
    PhoneNumberIdentifier,
    RecognizeInputType, FileSource
)


class ActionProcessor:

    def __init__(self, logger, call_connection_id, caller_id=None, call_automation_client=None, transfer_agent="",
                 correlation_id=""):
        self.call_connection_id = call_connection_id
        self.logger = logger
        self.caller_id = caller_id
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
                    case 3:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(self.call_connection_id, url_file, context=self.correlation_id)
                        time.sleep(duration / 1000.0)
                        self.handle_hangup()
                    case 50:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(self.call_connection_id, url_file, context=self.correlation_id, action="50")
                        time.sleep(duration / 1000.0)
                    case 21:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        self.logger.info(f"Transfer to -> {self.transfer_agent}")
                        self.transfer_call_to_agent(call_connection_id=self.call_connection_id,
                                                    agent_phone_number=self.transfer_agent)
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

    @staticmethod
    def parse_url(html_string):
        # Decode html to text
        text = unescape(html_string)
        return text
