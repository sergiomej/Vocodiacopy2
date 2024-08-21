import json
import sys
import time

from html import unescape


from azure.communication.callautomation import (
    PhoneNumberIdentifier,
    RecognizeInputType, FileSource, TextSource, SsmlSource, CommunicationUserIdentifier, CommunicationIdentifier, CallAutomationClient
)


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
                        self.handle_play(url_file)
                        time.sleep(duration / 1000.0)
                    case 1:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        self.handle_recognize(url=url_file)
                    case 2:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(url_file)
                        time.sleep(duration / 1000.0)
                        self.transfer_call_to_agent()
                    case 3:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(url_file)
                        time.sleep(duration / 1000.0)
                        self.handle_hangup()
                    case 20:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(url_file)
                        time.sleep(duration / 1000.0)
                        self.warm_transfer(call_connection_id=self.call_connection_id,
                                           agent_phone_number=self.transfer_agent)
                    case 21:
                        continue
                    case 50:
                        url_file = self.parse_url(asset["RecordingUrl"])
                        duration = asset["Duration_MS"]
                        self.handle_play(url_file, action="50")
                        time.sleep(duration / 1000.0)
                    case _:
                        self.logger.info(f"No valid action [{asset}]")
        except Exception as e:
            self.logger.error(e)
            line = sys.exc_info()[-1].tb_lineno
            self.logger.error("Error in line #{} Msg: {}".format(line, e))
            self.handle_hangup()

    def stop_all_media(self):
        self.call_automation_client.get_call_connection(
                self.call_connection_id).cancel_all_media_operations()

    def handle_recognize(self, url=None, text=None, history=None):
        self.logger.info(f"URL to play: {url}")
        play_source = None

        if url:
            play_source = FileSource(url=url)

        if text:
            ssml_to_play = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US"><voice name="en-US-AvaMultilingualNeural"><mstts:express-as role="YoungAdultFemale" style="customerservice" styledegree="2">{text}</mstts:express-as></voice></speak>'
            play_source = SsmlSource(ssml_text=ssml_to_play)

        operation_context = {
            "history": history,
            "did": self.did,
            "text": text
        }

        call_handler = self.call_automation_client.get_call_connection(self.call_connection_id)
        # call_handler.play_media(play_source=play_source, play_to="all")

        ssml_silence = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US"><voice name="en-US-AvaMultilingualNeural"><break time="3s"/></voice></speak>'
            # play_prompt=SsmlSource(ssml_text=ssml_silence),
        self.call_automation_client.get_call_connection(
            self.call_connection_id).start_recognizing_media(
            play_prompt=play_source,
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier(self.caller_id),
            initial_silence_timeout=60,
            end_silence_timeout=1,
            interrupt_call_media_operation=True,
            interrupt_prompt=True,
            operation_context=json.dumps(operation_context))

        self.logger.info("Recognising media started.")

    def handle_play(self, url=None, action=""):
        self.logger.info(f"URL to play: {url}")
        self.logger.info(f"Action: {action}")

        operation_context = {
            "correlation_id": self.correlation_id,
            "action": action,
            "did": self.did
        }

        # TODO: Needs to play to a specific participant
        # play_to = PhoneNumberIdentifier(self.caller_id)

        play_source = FileSource(url=url)
        self.call_automation_client.get_call_connection(self.call_connection_id).play_media_to_all(play_source,
                                                                                                   operation_context=json.dumps(
                                                                                                       operation_context))

    def handle_play_text(self, call_connection_id, text=None, context=None, action=None):
        self.logger.info(f"Text to play: {text}")
        self.logger.info(f"Action: {action}")

        play_source = TextSource(text=text, voice_name="en-US-AriaNeural")
        self.call_automation_client.get_call_connection(call_connection_id).play_media_to_all(play_source,
                                                                                              operation_context=context)
        time.sleep(3)

    def handle_hangup(self):
        self.call_automation_client.get_call_connection(self.call_connection_id).hang_up(is_for_everyone=True)

    def transfer_call_to_agent(self, transfer_agent=None, connection_string=None, callback_uri=None):
        try:
            self.logger.info(f"Init transfer to: {transfer_agent}")
            if not transfer_agent or transfer_agent.isspace():
                self.logger.info("Agent phone number is empty")
                self.handle_play_text(call_connection_id=self.call_connection_id, text="No agent to transfer")
            else:
                self.logger.info(f"caller: {self.caller_id} did: {self.did}")
                caller_id_number = PhoneNumberIdentifier(self.did)
                sip_headers = {}
                sip_headers["User-To-User"] = "value"
                sip_headers["X-MS-Custom-headerName"] = "headerValue"
                target = PhoneNumberIdentifier(transfer_agent)
                call_connection_client = self.call_automation_client.get_call_connection(
                    call_connection_id=self.call_connection_id)

                call_prop = call_connection_client.get_call_properties()

                self.logger.info(f"Call state: {call_prop.call_connection_state}")

                result = call_connection_client.add_participant(
                    target,
                    sip_headers=sip_headers,
                    source_caller_id_number=caller_id_number
                )

                self.logger.info(f"Transfer call initiated to agent {result}")

        except Exception as ex:
            self.logger.error(f"Error transferring call to agent: {ex}")

    def warm_transfer(self, call_connection_id, agent_phone_number):
        try:
            # call_automation_client_p = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
            transfer_destination = PhoneNumberIdentifier(agent_phone_number)
            source = PhoneNumberIdentifier(self.did)

            self.logger.info(f"Caller phone number: {self.caller_id}")
            self.logger.info(f"DID phone number: {self.did}")

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
