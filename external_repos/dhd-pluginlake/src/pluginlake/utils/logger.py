"""module for standard logging"""

import logging
import os
from typing import Optional


def setup_logger(log_file: str, log_level: Optional[str] = "INFO", verbose: bool = False):
    """Setup logger"""
    log_level = log_level or os.getenv("LOG_LEVEL", "INFO")
    log_level = log_level.upper()
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_date_format = "%Y-%m-%d %H:%M:%S"
    log_formatter = logging.Formatter(log_format, datefmt=log_date_format)
    logger = logging.getLogger()
    logger.setLevel(log_level)
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        logger.addHandler(console_handler)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    return logger
