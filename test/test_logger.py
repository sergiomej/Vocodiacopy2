from util.logger_manager import LoggerManager


def test_logger_manager():
    logger = LoggerManager(logger_name="test_logger", log_file="/tmp/test.log").handler()
    logger.info("hi")
    assert isinstance(logger, LoggerManager)
