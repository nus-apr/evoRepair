import os
import time
import argparse
import traceback
import signal
import multiprocessing as mp
import app.utilities
from app import emitter, logger, values, repair, builder, tester, validator, utilities
from app.configuration import  Configurations
from app.patch import IndexedPatch
from app.test_suite import IndexedTest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import OrderedDict


class Interval:
    def __init__(self, start, end):
        self.start = start
        self.end = end


class Timer:
    def __init__(self):
        self.time_intervals = OrderedDict()

    def start_phase(self, phase):
        if self.__exists(phase):
            raise ValueError(f"Phase {phase} already exists")

        self.time_intervals[phase] = [Interval(time.time(), None)]

    def pause_phase(self, phase):
        if not self.__exists(phase):
            raise ValueError(f"Phase {phase} does not exist")
        if not self.__is_running(phase):
            raise ValueError(f"Phase {phase} is already paused")

        self.time_intervals[phase][-1].end = time.time()

    def pause_all(self):
        end_time = time.time()
        for intervals in self.time_intervals.values():
            intervals[-1].end = end_time

    def resume_phase(self, phase):
        if not self.__exists(phase):
            raise ValueError(f"Phase {phase} does not exist")
        if self.__is_running(phase):
            raise ValueError(f"Phase {phase} is already running")

        self.time_intervals[phase].append(Interval(time.time(), None))

    def summarize(self):
        for phase, intervals in self.time_intervals.items():
            if intervals[-1].end is None:
                raise RuntimeError(f"Phase {phase} is still running; cannot summarize.")

        return OrderedDict([
            (phase, sum(map(lambda interval: interval.end - interval.start, intervals)))
            for phase, intervals in self.time_intervals.items()
        ])

    def __exists(self, phase):
        return phase in self.time_intervals

    def __is_running(self, phase):
        assert self.__exists(phase)

        return self.time_intervals[phase][-1].end is None


timer = Timer()

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
    global timer
    phase = "Startup"
    timer.start_phase(phase)

    create_directories()
    logger.create_log_files()

    timer.pause_phase(phase)
    phase = "Bootstrap"
    timer.start_phase(phase)

    bootstrap(arg_list)

    timer.pause_phase(phase)
    phase = "Build"
    timer.start_phase(phase)

    emitter.sub_title("Build Project")
    builder.clean_project(values.dir_exp, values.cmd_clean)
    builder.config_project(values.dir_exp, values.cmd_pre_build)
    builder.build_project(values.dir_exp, values.cmd_build)

    timer.pause_phase(phase)
    phase = "Testing"
    timer.start_phase(phase)

    emitter.sub_title("Test Diagnostics")
    tester.generate_test_diagnostic()

    timer.pause_phase(phase)

    while utilities.have_budget(values.time_duration_total):
        values.iteration_no = values.iteration_no + 1
        emitter.sub_title("Iteration #{}".format(values.iteration_no))

        dry_run_repair = False
        num_patches_wanted = 5
        patch_gen_timeout_in_secs = 1200

        dry_run_test_gen = False
        test_gen_timeout_per_class_in_secs = 20

        compile_patches = True
        compile_tests = True
        execute_tests = True

        dir_patches = Path(values.dir_info["patches"], f"gen{values.iteration_no}")
        dir_tests = Path(values.dir_info["gen-test"], f"gen{values.iteration_no}")
        dir_validation = Path(values.dir_output, f"validate-gen{values.iteration_no}")

        directories = (dir_patches, dir_tests, dir_validation)
        non_empty_conditions = (dry_run_repair, dry_run_test_gen, not compile_patches and not compile_tests)
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
        for condition, directory in zip(non_empty_conditions, directories):
            if not condition:
                utilities.check_is_empty_dir(directory)

        phase = "Patch Generation"
        if values.iteration_no == 1:
            timer.start_phase(phase)
        else:
            timer.resume_phase(phase)

        patches = repair.generate(values.dir_info["source"], values.dir_info["classes"],
            values.dir_info["tests"], values.dir_info["deps"], dir_patches,
            num_patches_wanted=num_patches_wanted, timeout_in_seconds=patch_gen_timeout_in_secs, dry_run=dry_run_repair
        )
        indexed_patches = [IndexedPatch(values.iteration_no, patch) for patch in patches]

        timer.pause_phase(phase)
        phase = "Test Generation"
        if values.iteration_no == 1:
            timer.start_phase(phase)
        else:
            timer.resume_phase(phase)

        tests = tester.generate_additional_test(current_indexed_patches, dir_tests,
                                                    timeout_per_class_in_seconds=test_gen_timeout_per_class_in_secs,
                                                    dry_run=dry_run_test_gen)
        indexed_tests = [IndexedTest(values.iteration_no, test) for test in tests]

        timer.pause_phase(phase)
        phase = "Validation"
        if values.iteration_no == 1:
            timer.start_phase(phase)
        else:
            timer.resume_phase(phase)

        _ = validator.validate(indexed_patches, indexed_tests, dir_validation, compile_patches=compile_patches,
                               compile_tests=compile_tests, execute_tests=execute_tests)

        timer.pause_phase(phase)


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
    except Exception as e:
        timer.pause_all()

        is_error = True
        emitter.error("Runtime Error")
        emitter.error(str(e))
        logger.error(traceback.format_exc())
    finally:
        emitter.end(timer, is_error)
        logger.store_logs()
        if is_error:
            exit(1)
