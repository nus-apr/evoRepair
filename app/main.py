import asyncio
import itertools
import json
import os
import time
import argparse
import traceback
import signal
import multiprocessing as mp
import socket

import app.utilities
from app import emitter, logger, values, repair, builder, tester, validator, utilities
from app.configuration import  Configurations
from app.patch import IndexedPatch
from app.test_suite import IndexedTest, TestSuite, Test
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import OrderedDict, Counter, defaultdict

from app.tester import read_evosuite_version
from app.validator import validate


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


async def run(arg_list):
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

    i_patch_population_size = 3
    i_test_population_size = 20

    assert values.iteration_no == 0, f"values.iteration_no is {values.iteration_no}, expected 0"

    hall_of_fame_i_patches = set()
    perfect_i_patches = set()
    all_i_tests = set()
    kill_matrix = defaultdict(set)  # IndexedPatch |-> set(IndexedTest)

    evosuite_goal_i_patches = set()

    def get_reply_str(reply, dump_path, length_limit=1024):
        reply_str = json.dumps(reply)

        if len(reply_str) > length_limit:
            wrapper_reply = get_wrapper_reply(reply_str, dump_path)
            final_reply_str = json.dumps(wrapper_reply)
            dumped = True

            if len(final_reply_str) > length_limit:
                raise RuntimeError(
                    f"wrapped reply still too long ({len(final_reply_str)} bytes; limit is {length_limit} bytes);"
                    f" see dumped reply at {str(dump_path)}")
        else:
            final_reply_str = reply_str
            dumped = False

        return dumped, final_reply_str

    def get_wrapper_reply(reply_str, dump_path):
        assert os.path.isabs(dump_path), str(dump_path)
        assert not os.path.exists(dump_path), str(dump_path)

        with open(dump_path, 'w') as f:
            f.write(reply_str)

        return {
            "cmd": "readJsonFile",
            "data": {
                "path": str(dump_path)
            }
        }

    async def handle_get_patch_pool(json_data, writer):
        def get_patch_pool():
            return [{"index": str(i_patch)} for i_patch in evosuite_goal_i_patches]

        print('[Server] Sending patch pool.')

        reply = {
            "cmd": json_data["cmd"],
            "data": get_patch_pool()
        }

        dump_path = Path("/", "tmp", f"{reply['cmd']}{values.iteration_no}.json")
        _, final_reply_str = get_reply_str(reply, dump_path)

        writer.write(final_reply_str.encode("utf-8"))
        await writer.drain()

    async def handle_get_kill_matrix_and_new_goals(json_data, writer):
        population = json_data['data']['generation']
        test_names = json_data['data']['tests']
        junit_class = json_data['data']['classname']
        test_path = json_data['data']['testSuitePath']
        scaffolding_path = json_data['data']['testScaffoldingPath']

        suite_dir_src = Path(test_path).parents[len(junit_class.split(".")) - 1]

        dir_evosuite = Path(values._dir_root, "extern", "evosuite")
        evosuite_jar = Path(dir_evosuite, "master", "target", f"evosuite-master-{read_evosuite_version()}.jar")
        assert os.path.isfile(evosuite_jar), evosuite_jar

        evosuite_runtime_jar = Path(dir_evosuite, "standalone_runtime", "target",
                                    f"evosuite-standalone-runtime-{read_evosuite_version()}.jar")
        assert os.path.isfile(evosuite_runtime_jar), evosuite_runtime_jar
        junit_jar = Path(values._dir_root, "extern", "arja", "external", "lib", "junit-4.11.jar")
        assert os.path.isfile(junit_jar), junit_jar

        compile_deps = [evosuite_jar]

        runtime_deps = [evosuite_runtime_jar, junit_jar]

        suite = TestSuite(suite_dir_src, junit_class, compile_deps, runtime_deps, key=junit_class)

        indexed_tests = [IndexedTest(values.iteration_no, Test(suite, test_name)) for test_name in test_names]

        dir_patches = Path(values.dir_info["patches"], f"gen{values.iteration_no}")
        dir_tests = Path(values.dir_info["gen-test"], f"gen{values.iteration_no}")
        dir_validation = Path(values.dir_output, f"validate-gen{values.iteration_no}")
        additional_tests_info_path = Path(values.dir_info["patches"], f"additional_tests_gen{values.iteration_no}.txt")

        patch_gen_timeout_in_secs = 1200

        validation_result = validate(evosuite_goal_i_patches, indexed_tests, dir_validation)

        reply_kill_matrix = defaultdict(list)
        useful_i_tests = set()

        num_killed_patches = 0

        for i_patch, _, failing_i_tests in validation_result:
            for i_test in failing_i_tests:
                reply_kill_matrix[i_test].append(i_patch)
                useful_i_tests.add(i_test)
            if failing_i_tests:
                if i_patch in perfect_i_patches:
                    perfect_i_patches.discard(i_patch)
                    hall_of_fame_i_patches.add(i_patch)
                    num_killed_patches += 1

        if useful_i_tests:
            all_i_tests.update(useful_i_tests)

            patches = repair.generate(values.dir_info["source"], values.dir_info["classes"],
                                      values.dir_info["tests"], values.dir_info["deps"],
                                      dir_patches, all_i_tests, additional_tests_info_path,
                                      num_patches_wanted=num_killed_patches,
                                      timeout_in_seconds=patch_gen_timeout_in_secs)
            indexed_patches = [IndexedPatch(values.iteration_no, patch) for patch in patches]
            perfect_i_patches.update(indexed_patches)

            # generate some new patches
            evosuite_goal_i_patches.clear()
            evosuite_goal_i_patches.update(perfect_i_patches)

        changed_lines4class = defaultdict(set)
        for i_patch in evosuite_goal_i_patches:
            fix_locations = i_patch.patch.get_fix_locations()
            for classname, lines in fix_locations.items():
                changed_lines4class[classname].update(lines)
        goal_fix_locations = [
            {"classname": classname, "targetLines": list(lines)}
            for classname, lines in changed_lines4class.items()
        ]

        reply = {
            "cmd": json_data["cmd"],
            "data": {
                "killMatrix": [
                    {"testName": i_test.method_name, "killedPatches": [str(i_patch) for i_patch in killed_i_patches]}
                    for i_test, killed_i_patches in reply_kill_matrix.items()
                ],
                "patches": [{"index": str(i_patch)} for i_patch in evosuite_goal_i_patches],
                "fixLocations": goal_fix_locations
            }
        }

        dump_path = Path("/", "tmp", f"{reply['cmd']}{values.iteration_no}.json")
        _, final_reply_str = get_reply_str(reply, dump_path)
        writer.write(final_reply_str.encode("utf-8"))
        await writer.drain()

        values.iteration_no += 1

    async def handle_unknown_command(json_data, writer):
        print(f"[Server] Unknown command: {json_data['cmd']}. Sending back echo.")

        reply = {k: v for k, v in json_data.items()}
        if "data" not in reply:
            reply["data"] = [4, 0, 4]

        writer.write(json.dumps(reply).encode("utf-8"))
        await writer.drain()

    async def evosuite_message_callback(reader, writer):
        while True:
            message = (await reader.read(1024)).decode("utf-8")

            json_data = json.loads(message)
            cmd = json_data["cmd"]
            if cmd == "readJsonFile":
                json_file_path = json_data["data"]["path"]
                with open(json_file_path) as f:
                    json_data = json.loads(f.read())
                    cmd = json_data["cmd"]

            dispatch = {
                "getPatchPool": handle_get_patch_pool,
                "getKillMatrixAndNewGoals": handle_get_kill_matrix_and_new_goals
            }

            if cmd in dispatch:
                await dispatch[cmd](json_data, writer)
            else:
                await handle_unknown_command(json_data, writer)

    while utilities.have_budget(values.time_duration_total):
        values.iteration_no = values.iteration_no + 1
        emitter.sub_title("Iteration #{}".format(values.iteration_no))

        dry_run_repair = False
        patch_gen_timeout_in_secs = 1200

        dry_run_test_gen = False
        test_gen_timeout_per_class_in_secs = 20

        compile_patches = True
        compile_tests = True
        execute_tests = True

        dir_patches = Path(values.dir_info["patches"], f"gen{values.iteration_no}")
        dir_tests = Path(values.dir_info["gen-test"], f"gen{values.iteration_no}")
        dir_validation = Path(values.dir_output, f"validate-gen{values.iteration_no}")
        additional_tests_info_path = Path(values.dir_info["patches"], f"additional_tests_gen{values.iteration_no}.txt")

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

        while len(perfect_i_patches) < i_patch_population_size:
            patches = repair.generate(values.dir_info["source"], values.dir_info["classes"],
                values.dir_info["tests"], values.dir_info["deps"], dir_patches, all_i_tests, additional_tests_info_path,
                num_patches_wanted=i_patch_population_size - len(perfect_i_patches),
                timeout_in_seconds=patch_gen_timeout_in_secs, dry_run=dry_run_repair
            )

            perfect_i_patches.update([IndexedPatch(values.iteration_no, patch) for patch in patches])

            values.iteration_no += 1

        evosuite_goal_i_patches.update(perfect_i_patches)
        changed_lines4class = defaultdict(set)
        for i_patch in evosuite_goal_i_patches:
            fix_locations = i_patch.patch.get_fix_locations()
            for classname, lines in fix_locations.items():
                changed_lines4class[classname].update(lines)
        goal_fix_locations = [
            {"classname": classname, "targetLines": list(lines)}
            for classname, lines in changed_lines4class.items()
        ]

        fix_location_file = Path(values.dir_output, "init_locations.json")
        with open(fix_location_file, 'w') as f:
            json.dump(goal_fix_locations, f)

        print(f"fix locations in {str(fix_location_file)}")

        server_socket = socket.socket()
        server_socket.bind(("localhost", 0))
        _, port = server_socket.getsockname()
        print(f"listening on port {port}")
        server = await asyncio.start_server(evosuite_message_callback, sock=server_socket)
        async with server:
            await server.start_serving()
            # start evosuite here

            tester.generate_additional_test(evosuite_goal_i_patches, dir_tests, f"_gen_{values.iteration_no}_ESTest")

            #process = await asyncio.create_subprocess_shell(evosuite_command)

            task = asyncio.create_task(server.serve_forever())
            await task


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
    args = parser.parse_args()
    return args

def main():
    parsed_args = parse_args()
    is_error = False
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        asyncio.run(run(parsed_args))
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
