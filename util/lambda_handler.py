import json

import requests


class LambdaHandler:
    @staticmethod
    def lambda_handler(logger, message, history, caller_id):
        try:
            url = "https://vocodia-aria-junior.azurewebsites.net/api/agent"
            data = {"prompt": message, "history": history, "chat": "2", "caller_id": caller_id}

            headers = {
                'Content-Type': 'application/json',
            }

            response = requests.post(url, data=json.dumps(data), headers=headers)

            return response
        except Exception as e:
            logger.error(e)
