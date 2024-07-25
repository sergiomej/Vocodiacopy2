import sys
import time
import asyncio
import uuid

from html import unescape
from urllib.parse import urlencode

from azure.communication.callautomation import (
    PhoneNumberIdentifier,
    CallAutomationClient,
    CommunicationIdentifier
)

COGNITIVE_SERVICE_ENDPOINT = "https://testaivocodia.cognitiveservices.azure.com/"
CALLBACK_URI_HOST = "https://switch.ngrok.dev"
CALLBACK_EVENTS_URI = CALLBACK_URI_HOST + "/api/callbacks"
ACS_CONNECTION_STRING = "endpoint=https://communication-disa-test.unitedstates.communication.azure.com/;accesskey=o4eO9kiaTeFSCGX1ka7h5HNbGdTqVQH0sFLSKQWblmtkW81zjn86JQQJ99AFACULyCphSYATAAAAAZCSFls1"


def warm_transfer():
    try:
        call_automation_client_p = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        source = PhoneNumberIdentifier("+18332866392")

        guid = uuid.uuid4()
        query_parameters = urlencode({"callerId": "+573044336760", "did": "+18332866392"})
        callback_uri = f"{CALLBACK_EVENTS_URI}/{guid}?{query_parameters}"

        new_call_connection = call_automation_client_p.create_call(source_caller_id_number=source,
                                                                   target_participant=PhoneNumberIdentifier("+573044336760"),

                                                                   callback_url=callback_uri)

    except Exception as ex:
        print(f"Error transferring call to agent: {ex}")

warm_transfer()