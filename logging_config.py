import logging
import sys

def setup_logging():
    """
    Configure structured logging for the application.
    """
    # Create logger
    logger = logging.getLogger("pipedesk_drive")
    logger.setLevel(logging.INFO)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    if not logger.handlers:
        logger.addHandler(handler)

    return logger

logger = setup_logging()
