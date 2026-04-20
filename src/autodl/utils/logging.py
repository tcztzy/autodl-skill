"""Logging setup for AutoDL."""

import logging
import os.path
import sys
from os import PathLike
from logging.handlers import TimedRotatingFileHandler

verbose_formatter: logging.Formatter = logging.Formatter(
    "[%(asctime)s][%(levelname)s][%(name)s][%(filename)s:%(lineno)d]%(message)s"
)
simple_formatter: logging.Formatter = logging.Formatter(
    fmt="[%(levelname)s][%(asctime)s]%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(logger_name: str, logs_dir: str | PathLike[str]) -> logging.Logger:
    """Create a logger that writes to stdout and rotating log files.

    Args:
        logger_name: Logger name.
        logs_dir: Directory where log files are written.

    Returns:
        Configured logger.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    # 屏幕
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(simple_formatter)
    logger.addHandler(stream_handler)
    # 文件
    handlers = (
        (logging.DEBUG, "main.log", verbose_formatter),
        (logging.INFO, "output.log", simple_formatter),
    )
    for level, filename, formatter in handlers:
        file_handler = TimedRotatingFileHandler(
            filename=os.path.join(logs_dir, filename),
            when="D",
            backupCount=5,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger
