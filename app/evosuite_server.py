from app import emitter, utilities, values
from app.uniapr import run_uniapr
from app.test_suite import TestSuite, Test, IndexedTest
from app.tester import read_evosuite_version
from app.validator import validate

import os
from pathlib import Path
from subprocess import PIPE, DEVNULL
import itertools
import socket
import json
import glob
import asyncio
import shutil
import pprint
from collections import defaultdict
import itertools

hall_of_fame_i_patches = set()
perfect_i_patches = set()
all_i_tests = set()
kill_matrix = defaultdict(set)  # IndexedPatch |-> set(IndexedTest)

evosuite_goal_i_patches = set()


async def main():
    global hall_of_fame_i_patches, perfect_i_patches, all_i_tests, kill_matrix, evosuite_goal_i_patches

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

        dir_src = Path(test_path).parents[len(junit_class.split(".")) - 1]

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

        suite = TestSuite(dir_src, junit_class, compile_deps, runtime_deps, key=junit_class)

        indexed_tests = [IndexedTest(values.iteration_no, Test(suite, test_name)) for test_name in test_names]

        dir_validation = Path(values.dir_output, f"validate-gen{values.iteration_no}")

        validation_result = validate(evosuite_goal_i_patches, indexed_tests, dir_validation)

        reply_kill_matrix = defaultdict(list)
        useful_i_tests = set()

        for i_patch, _, failing_i_tests in validation_result:
            for i_test in failing_i_tests:
                reply_kill_matrix[i_test].append(i_patch)
                useful_i_tests.add(i_test)
            if failing_i_tests:
                perfect_i_patches.remove(i_patch)
                hall_of_fame_i_patches.add(i_patch)

        if useful_i_tests:
            all_i_tests.update(useful_i_tests)

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

    server_socket = socket.socket()
    server_socket.bind(("localhost", 0))
    _, port = server_socket.getsockname()
    server = await asyncio.start_server(evosuite_message_callback, sock=server_socket)
    async with server:
        await server.start_serving()
        # start evosuite here
        evosuite_command = ""

        #process = await asyncio.create_subprocess_shell(evosuite_command)

        task = asyncio.create_task(server.serve_forever())
    print("interaction done, now tearing down server")


def get_patch_validation_result(test_name, patch_id):
    if test_name == 'test1' and int(patch_id) == 7:
        validation_result = True
    else:
        validation_result = False

    return validation_result


if __name__ == '__main__':
    asyncio.run(main())
