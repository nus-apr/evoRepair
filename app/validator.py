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


def validate(indexed_patches, indexed_tests, work_dir, compile_patches=True, compile_tests=True, execute_tests=True):
    assert os.path.isabs(work_dir)
    assert os.path.isdir(work_dir)
    if compile_patches or compile_tests:
        utilities.check_is_empty_dir(work_dir)

    emitter.sub_sub_title("Validating Generated Patches")

    dir_patches_bin = Path(work_dir, "patches_bin")

    dir_tests_bin = Path(work_dir, "target", "test-classes")  # UniAPR accepts maven directory structure

    indexed_patch_to_bin_dir_name = {}

    os.makedirs(dir_patches_bin, exist_ok=True)
    if compile_patches:
        for p in indexed_patches:
            patch_index = p.get_index()
            out_dir = Path(dir_patches_bin, f"gen{patch_index.generation}_{patch_index.key}")

            os.makedirs(out_dir)

            p.patch.compile(out_dir)

            indexed_patch_to_bin_dir_name[p] = out_dir.name

    unique_suites = {indexed_test.get_index()[:-1]: indexed_test.test.suite
                     for indexed_test in indexed_tests}.values()

    os.makedirs(dir_tests_bin, exist_ok=True)
    if compile_tests:
        for suite in unique_suites:
            suite.compile(dir_tests_bin)

    if values.use_hotswap:
        raise NotImplementedError("UniAPR validation for indexed patches has not been implemented")
        # changed_classes = list(itertools.chain(*(p.patch.changed_classes for p in indexed_patches)))
        # result = run_uniapr(work_dir, dir_patches_bin, changed_classes, execute_tests)
    else:
        tests_runtime_deps = set()
        for suite in unique_suites:
            tests_runtime_deps.update((str(Path(x).resolve()) for x in suite.runtime_deps))

        bin_dir_name_to_indexed_patch = dict(((v, k) for k, v in indexed_patch_to_bin_dir_name.items()))
        result = [(bin_dir_name_to_indexed_patch[bin_dir_name], passing_tests, failing_tests)
                  for bin_dir_name, passing_tests, failing_tests
                  in plain_validate(dir_patches_bin, dir_tests_bin, tests_runtime_deps, execute_tests)]

    emitter.debug(f"(patch_id, passing, failing): {pprint.pformat(result, indent=4)}")

    return result


def plain_validate(patches_bin_dir, tests_bin_dir, tests_runtime_deps, execute_tests):
    for x in patches_bin_dir, tests_bin_dir:
        assert os.path.isabs(x), str(x)
        assert os.path.isdir(x), str(x)
        if execute_tests:
            utilities.check_is_nonempty_dir(x)

    if not execute_tests:
        return []

    test_class_files = glob.glob(os.path.join(tests_bin_dir, "**", "*_ESTest.class"), recursive=True)
    test_classes = []
    for file in test_class_files:
        path = Path(file).relative_to(tests_bin_dir).with_suffix("")
        test_classes.append(".".join(path.parts))

    result = []

    for entry in os.scandir(patches_bin_dir):
        message = asyncio.run(run_plain_validator(entry.path, tests_bin_dir, tests_runtime_deps, test_classes))

        obj = json.loads(message)

        result.append((entry.name, obj["passingTests"], obj["failingTests"]))

    return result


async def run_plain_validator(patch_bin_dir, tests_bin_dir, tests_runtime_deps, test_classes):
    assert os.path.isabs(patch_bin_dir), str(patch_bin_dir)
    assert os.path.isabs(tests_bin_dir), str(tests_bin_dir)
    assert utilities.is_nonempty_dir(patch_bin_dir), str(patch_bin_dir)
    assert utilities.is_nonempty_dir(tests_bin_dir), str(tests_bin_dir)

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
                     , tests_bin_dir
                     , *tests_runtime_deps
                     ]

        for entry in os.scandir(values.dir_info["deps"]):
            assert entry.name.endswith(".jar"), f"the dependency {entry.path} is not jar file"
            classpath.append(entry.path)

        cp_str = ":".join((str(x) for x in classpath))

        command = (f'{java_executable} -cp "{cp_str}" evorepair.PlainValidator {port}'
                   f' {" ".join(test_classes)}')

        emitter.command(command)

        process = await asyncio.create_subprocess_shell(command, stdout=DEVNULL, stderr=PIPE)
        return_code = await process.wait()
        if return_code != 0:
            stderr = await process.stderr.read()
            utilities.error_exit("PlainValidator did not exit normally", stderr.decode("utf-8"),
                                 f"exit code is {return_code}")

    return result[0]
