import subprocess
import os
import sys
import signal
import random
from contextlib import contextmanager
from app import logger, emitter, values
import base64
import hashlib
import time


def execute_command(command, show_output=True):
    # Print executed command and execute it in console
    command = command.encode().decode('ascii', 'ignore')
    emitter.command(command)
    command = "{ " + command + " ;} 2> " + values.file_log_error
    if not show_output:
        command += " > /dev/null"
    # print(command)
    process = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True, env=os.environ)
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
        clean_command = "rm -rf " + values.dir_output
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


#def have_budget(time_budget):
#    if values.iteration_limit >= 0:
#        if values.iteration_no < values.iteration_limit:  # Only for testing purpose.
#            return True
#        else:
#            return False
#    else:
#        if values.timestamp_check is None:
#            values.timestamp_check = time.time()
#            return False
#        else:
#            time_start = values.timestamp_check
#            duration = float(format((time.time() - time_start) / 60, '.3f'))
#            if int(duration) > int(time_budget):
#                values.timestamp_check = None
#                return False
#        return True

def timed_out():
    return (values.time_system_end is not None
            and time.time() >= values.time_system_end)


def __dir_is_empty(path):
    assert os.path.isdir(path)
    return not any(os.scandir(path))


def is_empty_dir(path):
    return os.path.isdir(path) and __dir_is_empty(path)


def is_nonempty_dir(path):
    return os.path.isdir(path) and not __dir_is_empty(path)


def check_is_abspath(path, message=None):
    if message is None:
        message = f"{path} is not an absolute path"
    if not os.path.isabs(path):
        raise ValueError(message)


def check_is_dir(path, message=None):
    if message is None:
        message = f"{path} is not an existing directory"
    if not os.path.isdir(path):
        raise ValueError(message)


def check_is_nonempty_dir(path, message=None):
    if message is None:
        message = f"{path} is not a non-empty directory"
    if not is_nonempty_dir(path):
        raise ValueError(message)


def check_is_empty_dir(path, message=None):
    if message is None:
        message = f"{path} is not an empty directory"
    if not is_empty_dir(path):
        raise ValueError(message)

def test_gen_timed_out():
    return values.test_gen_total_timeout is not None and time.time() > values.time_test_gen_end
