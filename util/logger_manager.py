import logging


class LoggerManager:
    def __init__(self, logger_name: str = "switch_logger", log_file: str = "/var/log/call_log.log") -> object:

        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.DEBUG)

        # Create a stream handler
        stream_handler = logging.StreamHandler()
        stream_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        stream_handler.setFormatter(stream_formatter)
        self.logger.addHandler(stream_handler)

        # Create a file handler
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

    def handler(self):
        return self.logger
