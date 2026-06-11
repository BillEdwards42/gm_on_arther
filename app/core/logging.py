import logging
import json
import sys
from app.core.config import get_settings

settings = get_settings()

class GoogleCloudFormater(logging.Formatter):
    """
    Formats logs from cloud run as json
    Maps python log levels to google cloud severity levels.
    """

    def format(self, record):
        #1. Standardizing the log messages
        message = record.msg
        if record.args:
            message = message % record.args

        # 2. Map Python levels to Google Cloud levels
        # (Debug -> DEBUG, Info -> INFO, Warning -> WARNING, Error -> ERROR, Critical -> CRITICAL)
        severity_map = {
            'DEBUG': 'DEBUG',
            'INFO': 'INFO',
            'WARNING': 'WARNING',
            'ERROR': 'ERROR',
            'CRITICAL': 'CRITICAL'
        }

        # 3. Construct the JSON payload
        log_entry = {
            "severity": severity_map.get(record.levelname, 'INFO'),
            "message": message,
            "timestamp": self.formatTime(record, self.datefmt),
            "logger": record.name,
            "path": record.pathname,
            "line": record.lineno,
        }

        # 4. Handle exceptions (Stack Traces)
        if record.exc_info:
            log_entry['stack_trace'] = self.formatException(record.exc_info)

def setup_logging():
    """
    Configures the root logger to output json to std output.
    """
    # 1. Create a StreamHandler (writes to console/stdout)
    handler = logging.StreamHandler(sys.stdout)

    #2. Use our Custom JSON Formatter
    handler.setFormatter(GoogleCloudFormater())

    # 3. Get the Root Logger and apply settings
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    # Avoid adding duplicate handlers if this function is called twice
    if not root_logger.handlers:
        root_logger.addHandler(handler)

    # Silence "noisy" libraries (optional but recommended)
    logging.getLogger("uvicorn.access").disabled = True # Cloud Run handles access logs automatically

# Create a global logger instance for easy import
logger = logging.getLogger(settings.PROJECT_NAME)