from app import emitter, utilities, values
from app.uniapr import run_uniapr

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


"""
This is the function to implement the interfacing with UniAPR (optimized validation)

Expected Input
@arg list of patches
@arg list of test cases
@arg work_dir: a directory to which this function can write (but not overwrite) things

Expected Output
@output matrix of result for each test x patch
@output sorted list of plausible patches
@output ranked list of test-cases and their mutation score
"""

indexed_patch_to_bin_dir = {}

indexed_suite_to_bin_dir = {}


async def validate(indexed_patches, indexed_tests, work_dir, compile_patches=True, compile_tests=True, execute_tests=True):
    assert os.path.isabs(work_dir)
    assert os.path.isdir(work_dir)

    global indexed_suite_to_bin_dir, indexed_patch_to_bin_dir

    emitter.sub_sub_title("Validating Generated Patches")

    dir_patches_bin = Path(work_dir, "patches_bin")

    dir_tests_bin = Path(work_dir, "suites_bin")

    if compile_patches:
        for i_patch in indexed_patches:
            if i_patch not in indexed_patch_to_bin_dir:
                index = i_patch.get_index()
                out_dir = Path(dir_patches_bin, f"gen_{index.generation}_{index.key}")

                assert not out_dir.exists(), f"{str(out_dir)} already exists"
                os.makedirs(out_dir)

                i_patch.patch.compile(out_dir)

                indexed_patch_to_bin_dir[i_patch] = str(out_dir)

    if compile_tests:
        indexed_suites = set([it.indexed_suite for it in indexed_tests])

        for i_suite in indexed_suites:
            if i_suite not in indexed_suite_to_bin_dir:
                index = i_suite.get_index()
                out_dir = Path(dir_tests_bin, f"gen_{index.generation}_{index.key}")

                assert not out_dir.exists(), f"{str(out_dir)} already exists"
                os.makedirs(out_dir)

                i_suite.suite.compile(out_dir)

                indexed_suite_to_bin_dir[i_suite] = str(out_dir)

    if values.use_hotswap:
        raise NotImplementedError("UniAPR validation for indexed patches & tests has not been implemented")
    else:
        return await plain_validate(indexed_patches, indexed_tests)


async def plain_validate(indexed_patches, indexed_tests):
    # group indexed suites, so that any two suites in a same group do not have a same JUnit test class name
    indexed_suites = set([it.indexed_suite for it in indexed_tests])

    junit_2_i_suites = defaultdict(list)
    for i_suite in indexed_suites:
        junit_2_i_suites[i_suite.suite.junit_class].append(i_suite)

    i_suite_groups = []

    while junit_2_i_suites:
        i_suite_groups.append([i_suites.pop() for i_suites in junit_2_i_suites.values()])

        for junit in list(junit_2_i_suites.keys()):
            if not junit_2_i_suites[junit]:
                del junit_2_i_suites[junit]

    for group in i_suite_groups:
        junit_classes = [i_suite.suite.junit_class for i_suite in group]
        assert len(junit_classes) == len(set(junit_classes)), f"[{','.join([str(x) for x in group])}]"

    i_suite_2_i_tests = defaultdict(list)
    for i_test in indexed_tests:
        i_suite_2_i_tests[i_test.indexed_suite].append(i_test)

    result = []

    for i_patch in indexed_patches:

        passing_i_tests = []
        failing_i_tests = []

        patch_bin_dir = indexed_patch_to_bin_dir[i_patch]

        for i_suite_group in i_suite_groups:
            suites_bin_dirs = [indexed_suite_to_bin_dir[i_suite] for i_suite in i_suite_group]

            suites_runtime_deps = set(map(os.path.abspath,
                                          itertools.chain(
                                              *[i_suite.suite.runtime_deps for i_suite in i_suite_group])))

            i_test_group = itertools.chain(*[i_suite_2_i_tests[i_suite] for i_suite in i_suite_group])

            name2itest = {f"{it.indexed_suite.suite.junit_class}#{it.method_name}": it for it in i_test_group}

            message = await run_plain_validator(patch_bin_dir,
                                                suites_bin_dirs, suites_runtime_deps, list(name2itest.keys()))

            obj = json.loads(message)

            passing_i_tests.extend([name2itest[name] for name in obj["passingTests"]])
            failing_i_tests.extend([name2itest[name] for name in obj["failingTests"]])

        result.append((i_patch, passing_i_tests, failing_i_tests))

    return result


async def run_plain_validator(patch_bin_dir, suites_bin_dirs, suites_runtime_deps, full_test_names):
    assert os.path.isabs(patch_bin_dir), str(patch_bin_dir)
    assert utilities.is_nonempty_dir(patch_bin_dir), str(patch_bin_dir)
    for x in suites_bin_dirs:
        assert os.path.isabs(x), str(x)
        assert utilities.is_nonempty_dir(x), str(x)

    result = []

    async def plain_validator_connected(reader, _):
        result.append((await reader.read()).decode("utf-8"))

    server_socket = socket.socket()
    server_socket.bind(("localhost", 0))
    _, port = server_socket.getsockname()
    server = await asyncio.start_server(plain_validator_connected, sock=server_socket)
    async with server:
        await server.start_serving()

        java_executable = shutil.which("java")
        if java_executable is None:
            raise RuntimeError("java executable not found")

        plain_validator_jar = Path(values._dir_root, "extern", "plain-validator", "target",
                                   "plain-validator-1.0-SNAPSHOT-jar-with-dependencies.jar")
        assert plain_validator_jar.is_file(), str(plain_validator_jar)

        # must put patch_bin_dir before values.dir_info["classes"]
        classpath = [plain_validator_jar
                     , patch_bin_dir
                     , values.dir_info["classes"]
                     , *suites_bin_dirs
                     , *suites_runtime_deps
                     ]

        for entry in os.scandir(values.dir_info["deps"]):
            assert entry.name.endswith(".jar"), f"the dependency {entry.path} is not jar file"
            classpath.append(entry.path)

        cp_str = ":".join((str(x) for x in classpath))

        command = (f'{java_executable} -Ddefects4j.instrumentation.enabled=true -cp "{cp_str}" evorepair.PlainValidator {port}'
                   f' {" ".join(full_test_names)}')

        emitter.debug(command)
        emitter.normal(f"running {len(full_test_names)} test cases")

        process = await asyncio.create_subprocess_shell(command, stdout=DEVNULL, stderr=PIPE)
        return_code = await process.wait()
        if return_code != 0:
            stderr = await process.stderr.read()
            utilities.error_exit("PlainValidator did not exit normally", stderr.decode("utf-8"),
                                 f"exit code is {return_code}")

    return result[0]
