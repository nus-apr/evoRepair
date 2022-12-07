# -*- coding: utf-8 -*-

import time
import datetime
import os
import logging
from app import values
from shutil import copyfile
import logging

_logger_error:logging
_logger_command:logging
_logger_main:logging
_logger_build:logging

def setup_logger(name, log_file, level=logging.INFO, formatter=None):
    """To setup as many loggers as you want"""
    if formatter is None:
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


def create_log_files():
    global  _logger_main, _logger_build, _logger_command, _logger_error
    log_file_name = "log-" + str(time.time())
    log_file_path = values.dir_log_base + "/" + log_file_name
    values.file_log_main = log_file_path

    _logger_main = setup_logger("main", values.file_log_main)
    _logger_error = setup_logger("error", values.file_log_error)
    _logger_command = setup_logger("command", values.file_log_cmd)
    _logger_build = setup_logger("build", values.file_log_build)

def store_log_file(log_file_path):
    if os.path.isfile(log_file_path):
        copyfile(log_file_path, values.dir_log + "/" + log_file_path.split("/")[-1])


def store_logs():
    if os.path.isfile(values.file_log_main):
        copyfile(values.file_log_main, values.dir_log + "/log-latest")
    log_file_list = [
        values.file_log_cmd,
        values.file_log_build,
        values.file_log_cmd,
        values.file_log_main,
        values.file_log_crash
    ]
    for log_f in log_file_list:
        store_log_file(log_f)


def information(message):
    _logger_main.info(message)



def command(message):
    message = str(message).strip().replace("[command]", "")
    message = "[COMMAND]: " + str(message) + "\n"
    _logger_main.info(message)
    _logger_command.info(message)

def debug(message):
    message = str(message).strip()
    _logger_main.debug(message)


def error(message):
    _logger_main.error(message)
    _logger_error.error(message)


def note(message):
    message = str(message).strip().lower().replace("[note]", "")
    _logger_main.info(message)


def configuration(message):
    message = str(message).strip().lower().replace("[config]", "")
    message = "[CONFIGURATION]: " + str(message) + "\n"
    _logger_main.info(message)


def output(message):
    message = str(message).strip()
    message = "[OUTPUT]: " + message
    _logger_main.info(message)


def warning(message):
    message = str(message).strip().lower().replace("[warning]", "")
    _logger_main.warning(message)
