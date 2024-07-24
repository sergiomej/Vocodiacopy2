from datetime import datetime
import uuid


class CallEvent:
    def __init__(self,
                 correlation_id: str,
                 server_call_id: str,
                 phone: str,
                 start_at: str,
                 end_at: str,
                 action: str,
                 data: str):
        self.id = str(uuid.uuid4())
        self.correlation_id = correlation_id
        self.server_call_id = server_call_id
        self.phone = phone
        self.start = start_at
        self.end = end_at
        self.action = action
        self.data = data

    def to_dict(self):
        return {
            'id': self.id,
            'correlation_id': self.correlation_id,
            'server_call_id': self.server_call_id,
            'phone': self.phone,
            'start': self.start,
            'end': self.end,
            'action': self.action,
            'data': self.data
        }
