import subprocess
import os
import sys
import signal
import random
from contextlib import contextmanager
from app import logger, emitter, values, definitions
import base64
import hashlib
import time


def execute_command(command, show_output=True):
    # Print executed command and execute it in console
    command = command.encode().decode('ascii', 'ignore')
    emitter.command(command)
    command = "{ " + command + " ;} 2> " + definitions.FILE_ERROR_LOG
    if not show_output:
        command += " > /dev/null"
    # print(command)
    process = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True)
    (output, error) = process.communicate()
    # out is the output of the command, and err is the exit value
    return int(process.returncode)


def error_exit(*arg_list):
    emitter.error("Repair Failed")
    for arg in arg_list:
        emitter.error(str(arg))
    raise Exception("Error. Exiting...")


def clean_files():
    # Remove other residual files stored in ./output/
    emitter.information("Removing other residual files...")
    if os.path.isdir("output"):
        clean_command = "rm -rf " + definitions.DIRECTORY_OUTPUT
        execute_command(clean_command)


def backup_file(file_path, backup_path):
    backup_command = "cp " + file_path + " " + backup_path
    execute_command(backup_command)


def restore_file(file_path, backup_path):
    restore_command = "cp " + backup_path + " " + file_path
    execute_command(restore_command)


def reset_git(source_directory):
    reset_command = "cd " + source_directory + ";git reset --hard HEAD"
    execute_command(reset_command)


@contextmanager
def timeout(time):
    signal.signal(signal.SIGALRM, raise_timeout)
    signal.alarm(time)

    try:
        yield
    except TimeoutError:
        pass
    finally:
        signal.signal(signal.SIGALRM, signal.SIG_IGN)


def raise_timeout(signum, frame):
    raise TimeoutError


def check_budget(time_budget):
    if values.DEFAULT_ITERATION_LIMIT >= 0:
        if values.ITERATION_NO < values.DEFAULT_ITERATION_LIMIT:  # Only for testing purpose.
            return False
        else:
            return True
    else:
        if values.CONF_TIME_CHECK is None:
            values.CONF_TIME_CHECK = time.time()
            return False
        else:
            time_start = values.CONF_TIME_CHECK
            duration = float(format((time.time() - time_start) / 60, '.3f'))
            if int(duration) > int(time_budget):
                values.CONF_TIME_CHECK = None
                return True
        return False

