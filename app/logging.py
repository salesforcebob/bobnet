import logging
from pythonjsonlogger import jsonlogger


def configure_json_logging(level: int = logging.INFO) -> None:
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear existing handlers
    while logger.handlers:
        logger.handlers.pop()

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
