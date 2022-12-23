from app import emitter, utilities, values
from app.tester import read_evosuite_version
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


def validate(patches, tests, work_dir, compile_patches=True, compile_tests=True, execute_tests=True):
    assert os.path.isabs(work_dir)
    assert os.path.isdir(work_dir)
    if compile_patches or compile_tests:
        utilities.check_is_empty_dir(work_dir)

    emitter.sub_sub_title("Validating Generated Patches")

    dir_patches_bin = Path(work_dir, "patches_bin")

    dir_tests_bin = Path(work_dir, "target", "test-classes")  # UniAPR accepts maven directory structure

    os.makedirs(dir_patches_bin, exist_ok=True)
    if compile_patches:
        for p in patches:
            out_dir = Path(dir_patches_bin, p.key)

            os.makedirs(out_dir)

            p.compile(out_dir)

    os.makedirs(dir_tests_bin, exist_ok=True)
    if compile_tests:
        for t in tests:
            t.compile(dir_tests_bin)

    if values.use_hotswap:
        changed_classes = list(itertools.chain(*(p.changed_classes for p in patches)))
        result = run_uniapr(work_dir, dir_patches_bin, changed_classes, execute_tests)
    else:
        result = plain_validate(dir_patches_bin, dir_tests_bin, execute_tests)
    emitter.debug(f"(patch_id, passing, failing): {pprint.pformat(result, indent=4)}")
    return result


def plain_validate(patches_bin_dir, tests_bin_dir, execute_tests):
    for x in patches_bin_dir, tests_bin_dir:
        assert os.path.isabs(x), str(x)
        assert os.path.isdir(x), str(x)
        if not execute_tests:
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
        message = asyncio.run(run_plain_validator(entry.path, tests_bin_dir, test_classes))

        obj = json.loads(message)

        patch_key = entry.name
        result.append((patch_key, obj["passingTests"], obj["failingTests"]))

    return result


async def run_plain_validator(patch_bin_dir, tests_bin_dir, test_classes):
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

        evosuite_runtime_jar = Path(values._dir_root, "extern", "evosuite", "standalone_runtime",
                                    "target", f"evosuite-standalone-runtime-{read_evosuite_version()}.jar")
        assert evosuite_runtime_jar.is_file(), str(evosuite_runtime_jar)

        junit_jar = Path(values._dir_root, "extern", "arja", "external", "lib", "junit-4.11.jar")
        assert junit_jar.is_file(), str(junit_jar)

        plain_validator_jar = Path(values._dir_root, "extern", "plain-validator", "target",
                                   "plain-validator-1.0-SNAPSHOT-jar-with-dependencies.jar")
        assert plain_validator_jar.is_file(), str(plain_validator_jar)

        # must put patch_bin_dir before values.dir_info["classes"]
        classpath = [patch_bin_dir, values.dir_info["classes"], evosuite_runtime_jar,
                     junit_jar, plain_validator_jar, tests_bin_dir]

        for entry in os.scandir(values.dir_info["deps"]):
            assert entry.name.endswith(".jar"), f"the dependency {entry.path} is not jar file"
            classpath.append(entry.path)

        classpath = ":".join((str(x) for x in classpath))

        command = (f'{java_executable} -cp "{classpath}" evorepair.PlainValidator {port}'
                   f' {" ".join(test_classes)}')

        emitter.command(command)

        process = await asyncio.create_subprocess_shell(command, stdout=DEVNULL, stderr=PIPE)
        return_code = await process.wait()
        if return_code != 0:
            stderr = await process.stderr.read()
            utilities.error_exit("PlainValidator did not exit normally", stderr.decode("utf-8"),
                                 f"exit code is {return_code}")

    return result[0]
