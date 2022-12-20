import os
import time
import argparse
import traceback
import signal
import multiprocessing as mp
import app.utilities
from app import emitter, logger, values, repair, builder, tester, validator, utilities
from app.configuration import  Configurations
from datetime import datetime, timezone, timedelta
from pathlib import Path

start_time = 0
time_info = {
    "initialization": '0',
    "build": '0',
    "bootstrap": '0',
    "testing": '0',
    "evolution": '0',
    "localization": '0',
    "patch-generation": '0',
    "test-generation": '0',
    "validation": '0',
    "verify": '0',
    "total": '0'
    }

stop_event = mp.Event()


def create_directories():
    dir_list = [
        values.dir_tmp,
        values.dir_output_base,
        values.dir_log_base,
        values.dir_backup
    ]

    for dir_i in dir_list:
        if not os.path.isdir(dir_i):
            os.makedirs(dir_i)

def timeout_handler(signum, frame):
    emitter.error("TIMEOUT Exception")
    raise Exception("end of time")


def shutdown(signum, frame):
    global stop_event
    emitter.warning("Exiting due to Terminate Signal")
    stop_event.set()
    raise SystemExit


def bootstrap(arg_list):
    emitter.header("Starting " + values.tool_name + " (Co-Evolution for Java Repair) ")
    emitter.sub_title("Loading Configurations")
    config = Configurations()
    config.read_arg_list(arg_list)
    config.read_conf_file()
    config.update_configuration()
    config.prepare_experiment()
    config.print_configuration()
    values.arg_parsed = True
    app.utilities.have_budget(values.time_duration_total)


def run(arg_list):
    global start_time, time_info
    start_time = time.time()
    create_directories()
    logger.create_log_files()
    duration = format((time.time() - start_time) / 60, '.3f')
    time_info["initialization"] = str(duration)

    time_check = time.time()
    bootstrap(arg_list)
    duration = format((time.time() - time_check) / 60, '.3f')
    time_info["bootstrap"] = str(duration)

    time_check = time.time()
    emitter.sub_title("Build Project")
    builder.clean_project(values.dir_exp, values.cmd_clean)
    builder.config_project(values.dir_exp, values.cmd_pre_build)
    builder.build_project(values.dir_exp, values.cmd_build)
    duration = format((time.time() - time_check) / 60, '.3f')
    time_info["analysis"] = str(duration)

    time_check = time.time()
    emitter.sub_title("Test Diagnostics")
    tester.generate_test_diagnostic()
    duration = format((time.time() - time_check) / 60, '.3f')
    time_info["testing"] = str(duration)

    while utilities.have_budget(values.time_duration_total):
        values.iteration_no = values.iteration_no + 1
        emitter.sub_title("Iteration #{}".format(values.iteration_no))

        # avoid colons in dir names because they disturb classpaths
        now = datetime.now(tz=timezone(offset=timedelta(hours=8))).strftime("%y%m%d_%H%M%S")

        dir_patches = values.dir_info["patches"]
        dir_tests = values.dir_info["gen-test"]
        dir_validation = Path(values.dir_output, f"validate-{now}")

        if not values.is_debug:
            assert not dir_validation.exists(), f"{dir_validation.absolute()} already exists"
            os.makedirs(dir_validation)
        else:
            os.makedirs(dir_validation, exist_ok=True)

        time_check = time.time()
        list_patches = repair.generate(values.dir_info["source"], values.dir_info["classes"],
            values.dir_info["tests"], values.dir_info["deps"], dir_patches
        )
        duration = format(((time.time() - time_check) / 60 - float(values.time_duration_generate)), '.3f')
        time_info["patch-generation"] = str(duration)

        time_check = time.time()
        list_test = tester.generate_additional_test(list_patches, dir_tests)
        duration = format(((time.time() - time_check) / 60 - float(values.time_duration_generate)), '.3f')
        time_info["test-generation"] = str(duration)

        time_check = time.time()
        _ = validator.validate(list_patches, list_test, dir_validation)
        duration = format(((time.time() - time_check) / 60 - float(values.time_duration_generate)), '.3f')
        time_info["validation"] = str(duration)

def parse_args():
    parser = argparse.ArgumentParser(prog=values.tool_name, usage='%(prog)s [options]')
    parser._action_groups.pop()
    required = parser.add_argument_group('required arguments')
    required.add_argument('--config', help='configuration file for repair', required=True)

    optional = parser.add_argument_group('optional arguments')
    optional.add_argument('-d', '--debug', help='print debugging information',
                          action='store_true',
                          default=False)
    optional.add_argument('-c', '--cache', help='use cached information for the process',
                          action='store_true',
                          default=False)
    optional.add_argument('--no-hotswap', help='do not use hot swap for validation',
                          action='store_true',
                          default=False)
    args = parser.parse_args()
    return args

def main():
    parsed_args = parse_args()
    is_error = False
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        run(parsed_args)
    except SystemExit as e:
        total_duration = format((time.time() - start_time) / 60, '.3f')
        time_info[values.time_duration_total] = str(total_duration)
        emitter.end(time_info, is_error)
        logger.store_logs()
    except KeyboardInterrupt as e:
        total_duration = format((time.time() - start_time) / 60, '.3f')
        time_info[values.time_duration_total] = str(total_duration)
        emitter.end(time_info, is_error)
        logger.store_logs()
    except Exception as e:
        is_error = True
        emitter.error("Runtime Error")
        emitter.error(str(e))
        logger.error(traceback.format_exc())
    finally:
        # Final running time and exit message
        total_duration = format((time.time() - start_time) / 60, '.3f')
        time_info[values.time_duration_total] = str(total_duration)
        emitter.end(time_info, is_error)
        logger.store_logs()
        if is_error:
            exit(1)
        exit(0)
