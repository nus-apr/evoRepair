import csv
import itertools
import os
import sys
import time
import argparse
import traceback
import signal
import multiprocessing as mp
import app.utilities
from app import emitter, logger, values, repair, builder, tester, validator, utilities, oracle_extractor
from app.configuration import  Configurations
from app.patch import IndexedPatch
from app.test_suite import IndexedTest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import OrderedDict, Counter, defaultdict
import asyncio
from app.test_suite import TestSuite, IndexedSuite, Test, IndexedTest
from app.patch import Patch, IndexedPatch
import random
import json
from app.test_suite import USER_TEST_GENERATION
from app.spectra import Spectra


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
        for phase, intervals in self.time_intervals.items():
            if self.__is_running(phase):
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


def run(arg_list):
    global timer
    phase = "Startup"
    timer.start_phase(phase)

    bootstrap(arg_list)

    oracle_extractor.extract_oracle_locations()
    oracle_locations_file = Path(values.dir_output, "oracleLocations.json")
    assert os.path.isfile(oracle_locations_file), str(oracle_locations_file)

    i_patch_population_size = values.num_perfect_patches

    perfect_i_patches = set()
    fame_i_patches = set()
    generated_i_tests = set()
    kill_matrix = {}
    user_i_tests = set()
    passing_user_i_tests = []
    failing_user_i_tests = []
    plausible_i_patches = set()
    total_num_killed_patches = 0

    dir_statistics = Path(values.dir_output, "statistics")
    os.makedirs(dir_statistics, exist_ok=True)
    assert utilities.is_empty_dir(dir_statistics), str(dir_statistics)

    stat_file = Path(dir_statistics, "statistics.csv")
    assert not os.path.exists(stat_file), f"statistics file {str(stat_file)} already exists"

    field_names = ["Iteration", "#Hall-of-Fame", "#Plausible", "#Valid", "#Overfitting",
                   "Hall-of-Fame", "Plausible\\Hall-of-Fame", "Valid\\Plausible", "#Generated-Tests",
                   "#Generated-Killing-Tests"]
    width = max([len(field) for field in field_names])
    with open(stat_file, 'w', newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()

    dir_kill_matrices = Path(dir_statistics, "kill_matrices")
    os.makedirs(dir_kill_matrices)

    iteration_stats = []
    def report():
        stat = {
            "Iteration": values.iteration_no,
            "#Hall-of-Fame": len(perfect_i_patches),
            "#Plausible": len(plausible_i_patches),
            "#Valid": len(fame_i_patches) + len(perfect_i_patches),
            "#Overfitting": total_num_killed_patches,
            "Hall-of-Fame": ' '.join([x.get_index_str() for x in perfect_i_patches]),
            "Plausible\\Hall-of-Fame": ' '.join([x.get_index_str() for x in plausible_i_patches - perfect_i_patches]),
            "Valid\\Plausible": ' '.join([x.get_index_str() for x in fame_i_patches - plausible_i_patches]),
            "#Generated-Tests": len(generated_i_tests),
            "#Generated-Killing-Tests": len(set(kill_matrix.keys()) & generated_i_tests)
        }
        iteration_stats.append(stat)

        for key, value in stat.items():
            emitter.normal(f"{key:>{width}}: {value}")

        with open(stat_file, 'w', newline="") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(iteration_stats)

        with open(Path(dir_kill_matrices, f"kill_matrix_{values.iteration_no}.json"), 'w') as f:
            json.dump({i_test.get_index_str(): [x.get_index_str() for x in i_patches]
                       for i_test, i_patches in kill_matrix.items()},
                      f)

    dir_perfect_patches = Path(values.dir_output, "perfect-patches")
    os.makedirs(dir_perfect_patches, exist_ok=True)
    utilities.check_is_empty_dir(dir_perfect_patches), str(dir_perfect_patches)
    save_path_for_i_patch = {}

    dir_plausible_patches = Path(values.dir_output, "plausible-patches")
    os.makedirs(dir_plausible_patches, exist_ok=True)
    utilities.check_is_empty_dir(dir_plausible_patches), str(dir_plausible_patches)

    assert values.iteration_no == 0, f"values.iteration_no is {values.iteration_no}, expected 0"

    timer.pause_phase(phase)
    emitter.normal(f"\n\tUsed {timer.last_interval_duration(phase, unit='m'):.2f} minutes")

    phase = "Build"
    timer.start_phase(phase)

    emitter.sub_title("Build Project")
    builder.clean_project(values.dir_exp, values.cmd_clean)
    builder.config_project(values.dir_exp, values.cmd_pre_build)

    emitter.normal("compiling program")
    builder.build_project(values.dir_exp, values.cmd_build)

    timer.pause_phase(phase)
    emitter.normal(f"\n\tUsed {timer.last_interval_duration(phase, unit='m'):.2f} minutes")

    phase = "Test Scanning"
    timer.start_phase(phase)

    emitter.sub_title("Scanning Test Suite")

    # Scan user-provided tests
    dir_bin = values.dir_info["classes"]
    dir_tests_bin = values.dir_info["tests"]
    dir_deps = values.dir_info["deps"]

    dir_spectra_base = Path(values.dir_info["repair"], "spectra")
    os.makedirs(dir_spectra_base, exist_ok=True)
    assert utilities.is_empty_dir(dir_spectra_base), str(dir_spectra_base)

    dir_user_tests_spectra = Path(dir_spectra_base, "user")
    os.makedirs(dir_user_tests_spectra)
    spectra_file = Path(dir_user_tests_spectra, "spectra_user_tests.csv")
    test_scanning_log = Path(dir_user_tests_spectra, "test_scanning_log.txt")
    orig_tests_file = Path(dir_user_tests_spectra, "passing_user_tests.txt")
    final_tests_file = Path(dir_user_tests_spectra, "relevant_user_tests.txt")
    passing_user_tests, failing_user_tests = repair.arja_scan_and_filter_tests(
        values.dir_info["source"], values.dir_info["classes"], values.dir_info["tests"], values.dir_info["deps"],
        orig_tests_file, final_tests_file, spectra_file, test_scanning_log, source_version=values.source_version
    )

    spectra = Spectra()
    spectra.update(spectra_file)

    dir_test_src = "N/A"
    dump_file = None
    compile_deps = [entry.path for entry in os.scandir(dir_deps)]
    runtime_deps = compile_deps

    tests_in_class = defaultdict(list)
    for full_test_name in [*passing_user_tests, *failing_user_tests]:
        class_name, method_name = full_test_name.split("#")
        tests_in_class[class_name].append(method_name)

    for classname, method_names in tests_in_class.items():
        suite = TestSuite(dir_test_src, classname, dump_file, method_names, compile_deps, runtime_deps, key=classname)
        for method_name in method_names:
            test = Test(suite, method_name)
            i_test = IndexedTest(USER_TEST_GENERATION, test)
            user_i_tests.add(i_test)
            full_test_name = f"{classname}#{method_name}"
            assert full_test_name in passing_user_tests or full_test_name in failing_user_tests
            if full_test_name in passing_user_tests:
                passing_user_i_tests.append(i_test)
            else:
                failing_user_i_tests.append(i_test)

        # these are already compiled
        i_suite = IndexedSuite(USER_TEST_GENERATION, suite)
        validator.indexed_suite_to_bin_dir[i_suite] = dir_tests_bin

    emitter.information(f"Found {len(user_i_tests)} user test cases,"
                        f" of which {len(passing_user_i_tests)} are passing,"
                        f" {len(failing_user_i_tests)} are failing")

    if len(passing_user_i_tests) < values.passing_tests_partitions:
        emitter.information(f"passing-tests-partitions is changed from {values.passing_tests_partitions}"
                            f" to {len(passing_user_i_tests)} because there are too few passing user tests")
        values.passing_tests_partitions = len(passing_user_i_tests)

    timer.pause_phase(phase)
    emitter.normal(f"\n\tUsed {timer.last_interval_duration(phase, unit='m'):.2f} minutes")

    INT_MIN = -0x80000000
    INT_MAX = 0x7fffffff

    emitter.information("\n\tStarting co-evolution")

    while True:
        if values.num_iterations > 0:
            if values.iteration_no > values.num_iterations:
                break

        emitter.sub_title("Iteration #{}".format(values.iteration_no))

        num_partitions = values.iteration_no + 1

        dry_run_repair = values.dry_run_repair
        if num_partitions == 0:
            num_patches_wanted = values.valid_population_size
            num_fames_wanted = 0
        elif num_partitions < values.passing_tests_partitions:
            num_patches_wanted = i_patch_population_size - len(perfect_i_patches)
            num_fames_wanted = values.valid_population_size
        else:
            num_patches_wanted = i_patch_population_size - len(perfect_i_patches)
            num_fames_wanted = 0
        patch_gen_timeout_in_secs = values.patch_gen_timeout

        mutate_operators = values.mutate_operators
        mutate_variables = values.mutate_variables
        mutate_methods = values.mutate_methods

        use_arja = values.use_arja

        dry_run_test_gen = values.dry_run_test_gen
        test_gen_timeout_per_class_in_secs = values.test_gen_timeout

        compile_patches = True
        compile_tests = num_partitions >= values.passing_tests_partitions
        execute_tests = True

        dir_patches_base = Path(values.dir_info["repair"], f"gen{values.iteration_no}")
        dir_patches = Path(dir_patches_base, "test-adequate")
        dir_fames = Path(dir_patches_base, f"valid")
        dir_validation = Path(values.dir_output, "validation", f"gen{values.iteration_no}")

        dir_repair_args = Path(values.dir_info["repair"], f"gen{values.iteration_no}-args")
        test_names_path = Path(dir_repair_args, f"basic_tests.txt")
        additional_tests_info_path = Path(dir_repair_args, f"additional_tests.txt")
        perfect_summary_path = Path(dir_repair_args, f"perfect_summary.txt")
        fame_summary_path = Path(dir_repair_args, f"fame_summary.txt")
        dir_arja_tmp = Path(values.dir_info["repair"], "arja_tmp", f"gen{values.iteration_no}")
        repair_log_file = Path(values.dir_info["repair"], f"gen{values.iteration_no}_log.txt")

        dir_tests = Path(values.dir_info["test-gen"], f"gen{values.iteration_no}")
        dir_test_gen_args = Path(values.dir_info["test-gen"], f"gen{values.iteration_no}-args")
        target_patches_file = Path(dir_test_gen_args, f"target_patches.json")
        seed_tests_file = Path(dir_test_gen_args, f"seed_tests.json")

        directories = (dir_patches, dir_fames, dir_tests, dir_validation, dir_repair_args, dir_arja_tmp,
                       dir_test_gen_args)
        non_empty_conditions = (dry_run_repair, dry_run_repair, dry_run_test_gen,
                                not compile_patches and not compile_tests, dry_run_repair, dry_run_repair,
                                dry_run_test_gen)
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
        for condition, directory in zip(non_empty_conditions, directories):
            if not condition:
                utilities.check_is_empty_dir(directory)
        dir_gzoltar_data = Path(dir_repair_args, f"gzoltar-data")
        os.makedirs(dir_gzoltar_data)

        phase = "Patch Generation"
        if values.iteration_no == 0:
            timer.start_phase(phase)
        else:
            timer.resume_phase(phase)

        init_ratio_perfect = values.init_ratio_perfect
        init_ratio_fame = values.init_ratio_fame

        basic_i_tests = failing_user_i_tests
        delta_passing_user_i_tests = []
        if num_partitions < values.passing_tests_partitions:
            num_passing_user_tests = len(passing_user_i_tests) * num_partitions // values.passing_tests_partitions
            next_num_passing_user_tests = (len(passing_user_i_tests)
                                           * (num_partitions + 1)
                                           // values.passing_tests_partitions)

            delta_passing_user_i_tests = passing_user_i_tests[num_passing_user_tests:next_num_passing_user_tests]

            additional_i_tests = passing_user_i_tests[:num_passing_user_tests]

            emitter.normal(
                f"Will use {num_passing_user_tests} of {len(passing_user_i_tests)} passing user test cases"
                " for patch generation")
        else:
            additional_i_tests = [*passing_user_i_tests, *generated_i_tests]

        if values.no_change_localization:
            localization_ignored_tests = set([i_test.get_full_test_name() for i_test in generated_i_tests])
        else:
            localization_ignored_tests = set()

        if utilities.timed_out():
            report()
            break

        patches, fame_patches, failed_i_tests = repair.generate(
            values.dir_info["source"], values.dir_info["classes"],
            values.dir_info["tests"], values.dir_info["deps"], dir_patches,
            basic_i_tests, test_names_path,
            additional_i_tests, additional_tests_info_path,

            oracle_locations_file=oracle_locations_file,

            mutate_operators=mutate_operators, mutate_variables=mutate_variables, mutate_methods=mutate_methods,

            num_fames_wanted=num_fames_wanted, dir_fames=dir_fames,

            perfect_i_patches=perfect_i_patches, init_ratio_perfect=init_ratio_perfect,
            perfect_summary_path=perfect_summary_path,

            fame_i_patches=fame_i_patches, init_ratio_fame=init_ratio_fame,
            fame_summary_path=fame_summary_path,

            num_patches_wanted=num_patches_wanted, timeout_in_seconds=patch_gen_timeout_in_secs, dry_run=dry_run_repair,

            use_arja=use_arja,

            source_version=values.source_version,

            num_patches_forced=1,

            arja_random_seed=random.randint(INT_MIN, INT_MAX),
            evo_random_seed=random.randint(INT_MIN, INT_MAX),

            spectra=spectra, dir_gzoltar_data=dir_gzoltar_data,

            dir_tmp=dir_arja_tmp,

            log_file=repair_log_file,

            localization_ignored_tests=localization_ignored_tests
        )
        indexed_patches = [IndexedPatch(values.iteration_no, patch) for patch in patches]
        indexed_fame_patches = [IndexedPatch(values.iteration_no, fame_patch) for fame_patch in fame_patches]

        perfect_i_patches.update(indexed_patches)
        fame_i_patches.update(indexed_fame_patches)

        for i_patch in indexed_patches:
            save_path = Path(dir_perfect_patches, f"{i_patch.get_index_str()}.diff")
            assert i_patch not in save_path_for_i_patch, i_patch.get_index_str()
            save_path_for_i_patch[i_patch] = save_path
            os.symlink(os.path.relpath(i_patch.patch.diff_file, save_path.parent), save_path)

        new_plausible_i_patches = []
        if not delta_passing_user_i_tests:
            new_plausible_i_patches.extend(indexed_patches)
            for i_patch, i_tests in zip(indexed_fame_patches, failed_i_tests):
                if not i_tests & user_i_tests:
                    new_plausible_i_patches.append(i_patch)
        for i_patch in new_plausible_i_patches:
            plausible_i_patches.add(i_patch)
            save_path = Path(dir_plausible_patches, f"{i_patch.get_index_str()}.diff")
            os.symlink(os.path.relpath(i_patch.patch.diff_file, save_path.parent), save_path)

        timer.pause_phase(phase)
        emitter.normal(f"\n\t\tUsed {timer.last_interval_duration(phase, unit='m'):.2f} minutes")

        if delta_passing_user_i_tests:
            emitter.information(f"Skipping test generation because there are remaining user tests")
            emitter.information(f"Will validate perfect patches with {len(delta_passing_user_i_tests)} user tests")
            indexed_tests = delta_passing_user_i_tests
        else:
            if utilities.timed_out():
                report()
                break

            phase = "Test Generation"
            if num_partitions == values.passing_tests_partitions:
                timer.start_phase(phase)
            else:
                timer.resume_phase(phase)

            tests = tester.generate_additional_test(perfect_i_patches, dir_tests,
                                                    target_patches_file=target_patches_file,

                                                    seed_i_tests=generated_i_tests, seeds_file=seed_tests_file,
                                                    kill_matrix=kill_matrix,

                                                    junit_suffix=f"_gen{values.iteration_no}_ESTest",
                                                    timeout_per_class_in_seconds=test_gen_timeout_per_class_in_secs,
                                                    dry_run=dry_run_test_gen,

                                                    random_seed=random.randint(INT_MIN, INT_MAX))
            indexed_tests = [IndexedTest(values.iteration_no, test) for test in tests]
            generated_i_tests.update(indexed_tests)

            timer.pause_phase(phase)
            emitter.normal(f"\n\t\tUsed {timer.last_interval_duration(phase, unit='m'):.2f} minutes")

        if utilities.timed_out():
            report()
            break

        phase = "Validation"
        if values.iteration_no == 0:
            timer.start_phase(phase)
        else:
            timer.resume_phase(phase)

        validation_result, non_compilable_i_patches = validator.validate(perfect_i_patches, indexed_tests,
                                                                         dir_validation,
                                                                         compile_patches=compile_patches,
                                                                         compile_tests=compile_tests,
                                                                         execute_tests=execute_tests,
                                                                         use_d4j_instr=True)
        for i_patch in non_compilable_i_patches:
            emitter.warning(f"removing patch {str(i_patch)} from perfect patches because compilation failed")
            perfect_i_patches.remove(i_patch)
            assert i_patch in save_path_for_i_patch, i_patch.get_index_str()
            os.remove(save_path_for_i_patch[i_patch])

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

        if num_partitions + 1 == values.passing_tests_partitions:
            for i_patch in perfect_i_patches:
                plausible_i_patches.add(i_patch)
                save_path = Path(dir_plausible_patches, f"{i_patch.get_index_str()}.diff")
                os.symlink(os.path.relpath(i_patch.patch.diff_file, save_path.parent), save_path)

        if not delta_passing_user_i_tests:
            total_num_killed_patches += num_killed_patches

        emitter.normal(f"{num_killed_patches} perfect patch(es) are killed")

        spectra_dir = Path(values.dir_output, "spectra", f"gen{values.iteration_no}")
        os.makedirs(spectra_dir, exist_ok=True)
        test_names_path = Path(spectra_dir, "test_names.txt")
        orig_pos_tests_file = Path(spectra_dir, "orgTests.txt")
        spectra_file = Path(spectra_dir, "spectra.csv")
        log_file = Path(spectra_dir, "log.txt")
        assert not os.path.exists(test_names_path), str(test_names_path)
        assert not os.path.exists(spectra_file), str(spectra_file)
        assert not os.path.exists(log_file), str(log_file)

        emitter.information("Retriving spectra of generated tests")

        repair.arja_get_tests_spectra(
            values.dir_info["source"], values.dir_info["classes"],
            values.dir_info["tests"], values.dir_info["deps"],
            indexed_tests, test_names_path, orig_pos_tests_file, spectra_file, log_file,
            values.source_version)
        spectra.update(spectra_file)

        timer.pause_phase(phase)
        emitter.normal(f"\n\tUsed {timer.last_interval_duration(phase, unit='m'):.2f} minutes")

        report()
        if utilities.timed_out():
            break

        values.iteration_no = values.iteration_no + 1


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
    optional.add_argument('--use-hotswap', help='do not use hot swap for validation',
                          action='store_true',
                          default=False)
    optional.add_argument('--arja', help='use ARJA for patch generation instead',
                          action='store_true',
                          default=False)
    # optional.add_argument('--mutate-operators', help='try mutating operators when doing repair',
    #                       action='store_true',
    #                       default=False)
    # optional.add_argument('--mutate-variables', help='try mutating variables when doing repair',
    #                       action='store_true',
    #                       default=False)
    # optional.add_argument('--mutate-methods', help='try mutating methods when doing repair',
    #                       action='store_true',
    #                       default=False)
    optional.add_argument('--init-ratio-perfect', help='ratio of perfect patches in initial patch population',
                          action='store',
                          type=float,
                          default=0.5)
    optional.add_argument('--init-ratio-fame', help='ratio of user-test-adequate patches in initial patch population',
                          action='store',
                          type=float,
                          default=0.25)
    optional.add_argument('--num-perfect-patches', help='number of perfect patches to generate',
                          action='store',
                          type=int,
                          default=10)
    optional.add_argument('--patch-gen-timeout', help='timeout of each patch generation attempt in seconds',
                          action='store',
                          type=int,
                          default=600)
    optional.add_argument('--test-gen-timeout', help='timeout of each test generation attempt in seconds',
                          type=int,
                          default=60)
    optional.add_argument('--num-iterations', help='number of co-evolution iterations to run',
                          type=int,
                          default=0)
    optional.add_argument('--total-timeout', help='total timeout for running this tool',
                          type=int,
                          default=None)
    optional.add_argument('--dry-run-test', help='enable dry run for test',
                          action='store_true',
                          default=False)
    optional.add_argument('--dry-run-patch', help='enable dry run for test',
                          action='store_true',
                          default=False)
    optional.add_argument('--dir-patch', help='absolute path for directory with generated patches',
                          type=Path,
                          default=None)
    optional.add_argument('--dir-test', help='absolute path for directory with generated tests',
                          type=Path,
                          default=None)
    optional.add_argument('--passing-tests-partitions',
                          help='number of partitions to divide passing user test cases into',
                          type=int,
                          default=4)
    optional.add_argument('--valid-population-size',
                          help='number of valid patches to generate in each initial iterations',
                          type=int,
                          default=40)
    optional.add_argument('--random-seed',
                          help='seed of pseudorandom number generator',
                          type=int,
                          default=None)
    optional.add_argument('--no-change-localization',
                          help='do not use generated tests for fault localization',
                          action='store_true',
                          default=False)
    args = parser.parse_args()

    if args.num_iterations < args.passing_tests_partitions:
        utilities.error_exit("num-iterations should be greater than or equal to passing-tests-partitions")

    if args.num_iterations == 0 and args.total_timeout is None:
        utilities.error_exit("must set one of --num-iterations and --total-timeout")

    return args

def main():
    values.time_system_start = time.time()

    create_directories()
    logger.create_log_files()

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
