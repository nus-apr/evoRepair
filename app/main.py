import itertools
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
from collections import OrderedDict, Counter


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

    def last_interval_duration(self, phase, unit="s"):
        if not self.__exists(phase):
            raise ValueError(f"Phase {phase} does not exist")
        if self.__is_running(phase):
            raise ValueError(f"Phase {phase} is still running")
        if unit not in ("s", "m", "h"):
            raise ValueError(f'Unknown time unit "{unit}"')

        last_interval = self.time_intervals[phase][-1]
        duration = last_interval.end - last_interval.start
        if unit == "m":
            duration /= 60
        elif unit == "h":
            duration /= 3600
        return duration

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

    i_patch_population_size = 5

    perfect_i_patches = set()
    fame_i_patches = set()
    all_i_tests = set()
    kill_matrix = {}

    dir_perfect_patches = Path(values.dir_output, "perfect-patches")
    os.makedirs(dir_perfect_patches, exist_ok=True)
    utilities.check_is_empty_dir(dir_perfect_patches), str(dir_perfect_patches)
    save_path_for_i_patch = {}

    assert values.iteration_no == 0, f"values.iteration_no is {values.iteration_no}, expected 0"

    while utilities.have_budget(values.time_duration_total):
        values.iteration_no = values.iteration_no + 1
        emitter.sub_title("Iteration #{}".format(values.iteration_no))

        dry_run_repair = False
        num_patches_wanted = i_patch_population_size - len(perfect_i_patches)
        patch_gen_timeout_in_secs = 1200

        dry_run_test_gen = False
        test_gen_timeout_per_class_in_secs = 20

        compile_patches = True
        compile_tests = True
        execute_tests = True

        dir_patches = Path(values.dir_info["patches"], f"gen{values.iteration_no}")
        dir_fames = Path(values.dir_output, "fame-patches", f"gen{values.iteration_no}")
        dir_tests = Path(values.dir_info["gen-test"], f"gen{values.iteration_no}")
        dir_validation = Path(values.dir_output, f"validate-gen{values.iteration_no}")
        additional_tests_info_path = Path(values.dir_info["patches"], f"additional_tests_gen{values.iteration_no}.txt")
        perfect_summary_path = Path(values.dir_info["patches"], f"perfect_summary_gen{values.iteration_no}.txt")
        fame_summary_path = Path(values.dir_info["patches"], f"fame_summary_gen{values.iteration_no}.txt")
        target_patches_file = Path(values.dir_info["gen-test"], f"target_patches_gen{values.iteration_no}.json")
        seed_tests_file = Path(values.dir_info["gen-test"], f"seed_tests_gen{values.iteration_no}.json")

        directories = (dir_patches, dir_fames, dir_tests, dir_validation)
        non_empty_conditions = (dry_run_repair, dry_run_repair, dry_run_test_gen,
                                not compile_patches and not compile_tests)
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

        init_ratio_perfect = values.init_ratio_perfect
        init_ratio_fame = values.init_ratio_fame

        patches, fame_patches = repair.generate(
            values.dir_info["source"], values.dir_info["classes"],
            values.dir_info["tests"], values.dir_info["deps"], dir_patches,
            all_i_tests, additional_tests_info_path,
            dir_fames=dir_fames,

            perfect_i_patches=perfect_i_patches, init_ratio_perfect=init_ratio_perfect,
            perfect_summary_path=perfect_summary_path,

            fame_i_patches=fame_i_patches, init_ratio_fame=init_ratio_fame,
            fame_summary_path=fame_summary_path,

            num_patches_wanted=num_patches_wanted, timeout_in_seconds=patch_gen_timeout_in_secs, dry_run=dry_run_repair
        )
        indexed_patches = [IndexedPatch(values.iteration_no, patch) for patch in patches]
        indexed_fame_patches = [IndexedPatch(values.iteration_no, fame_patch) for fame_patch in fame_patches]

        perfect_i_patches.update(indexed_patches)
        for i_patch in indexed_patches:
            save_path = Path(dir_perfect_patches, f"{i_patch.get_index_str()}.diff")
            assert i_patch not in save_path_for_i_patch, i_patch.get_index_str()
            save_path_for_i_patch[i_patch] = save_path
            os.symlink(i_patch.patch.diff_file, save_path)
        fame_i_patches.update(indexed_fame_patches)

        timer.pause_phase(phase)
        emitter.normal(f"Used {timer.last_interval_duration(phase, unit='m'):.2f} minutes")
        phase = "Test Generation"
        if values.iteration_no == 1:
            timer.start_phase(phase)
        else:
            timer.resume_phase(phase)

        tests = tester.generate_additional_test(perfect_i_patches, dir_tests,
                                                target_patches_file=target_patches_file,

                                                seed_i_tests=all_i_tests, seeds_file=seed_tests_file,
                                                kill_matrix=kill_matrix,

                                                junit_suffix=f"_gen{values.iteration_no}_ESTest",
                                                timeout_per_class_in_seconds=test_gen_timeout_per_class_in_secs,
                                                dry_run=dry_run_test_gen)
        indexed_tests = [IndexedTest(values.iteration_no, test) for test in tests]

        all_i_tests.update(indexed_tests)

        timer.pause_phase(phase)
        emitter.normal(f"Used {timer.last_interval_duration(phase, unit='m'):.2f} minutes")
        phase = "Validation"
        if values.iteration_no == 1:
            timer.start_phase(phase)
        else:
            timer.resume_phase(phase)

        validation_result = validator.validate(perfect_i_patches, indexed_tests, dir_validation,
                                               compile_patches=compile_patches,
                                               compile_tests=compile_tests,
                                               execute_tests=execute_tests,
                                               use_d4j_instr=True)

        num_killed_patches = 0
        for i_patch, _, failing_i_tests in validation_result:
            if failing_i_tests:
                perfect_i_patches.remove(i_patch)
                assert i_patch in save_path_for_i_patch, i_patch.get_index_str()
                os.remove(save_path_for_i_patch[i_patch])

                fame_i_patches.add(i_patch)

                for i_test in failing_i_tests:
                    if i_test not in kill_matrix:
                        kill_matrix[i_test] = []
                    kill_matrix[i_test].append(i_patch)

                num_killed_patches += 1

        emitter.normal(f"{num_killed_patches} perfect patch(es) are killed")

        timer.pause_phase(phase)
        emitter.normal(f"Used {timer.last_interval_duration(phase, unit='m'):.2f} minutes")


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
    optional.add_argument('--arja', help='use ARJA for patch generation instead',
                          action='store_true',
                          default=False)
    optional.add_argument('--init-ratio-perfect', help='ratio of perfect patches in initial patch population',
                          action='store',
                          type=float,
                          default=0)
    optional.add_argument('--init-ratio-fame', help='ratio of user-test-adequate patches in initial patch population',
                          action='store',
                          type=float,
                          default=0)
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
    except KeyboardInterrupt:
        timer.pause_all()

        emitter.information("Repair process stopped by user")
    finally:
        emitter.end(timer, is_error)
        logger.store_logs()
        if is_error:
            exit(1)
