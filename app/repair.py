import itertools
import shlex
import time

from app import emitter, utilities, values
from app.patch import Patch
from app.validator import indexed_suite_to_bin_dir

import os
from pathlib import Path
import glob
import shutil
import re
import subprocess
from subprocess import PIPE, DEVNULL
import math
import socket
import asyncio
import json

"""
This is the function to implement the interface with EvoRepair and ARJA(APR Tool)

Expected Inputs
@arg dir_src : directory of source files
@arg dir_bin: directory of class files
@arg dir_test_bin: directory of test files
@arg dir_deps: directory for dependencies
@arg dir_patches: directory for generated patches

Expected Output
@output list of patch objects [patch_1, patch_2]
Each patch objects has the following
    patch_1:
        diff_file_path
        
"""


def generate(dir_src, dir_bin, dir_test_bin, dir_deps, dir_patches,
             indexed_tests, additional_tests_info_path,
             mutate_operators=False, mutate_variables=False, mutate_methods=False,
             dir_fames=None,
             perfect_i_patches=None, init_ratio_perfect=None, perfect_summary_path=None,
             fame_i_patches=None, init_ratio_fame=None, fame_summary_path=None,
             num_patches_wanted=5, timeout_in_seconds=1200, dry_run=False,
             use_arja=False
             ):
    for x in dir_src, dir_bin, dir_test_bin, dir_deps:
        if x:
            assert os.path.isabs(x), x
            assert utilities.is_nonempty_dir(x), x
    assert os.path.isabs(dir_patches), dir_patches
    assert os.path.isdir(dir_patches), dir_patches
    assert os.path.isabs(additional_tests_info_path), additional_tests_info_path
    if not dry_run:
        utilities.check_is_empty_dir(dir_patches)
        assert Path(dir_patches) not in Path(additional_tests_info_path).parents

        if dir_fames is not None:
            utilities.check_is_empty_dir(dir_fames)

        assert not os.path.exists(additional_tests_info_path), additional_tests_info_path
    indexed_suites = set([it.indexed_suite for it in indexed_tests])
    for i_suite in indexed_suites:
        assert i_suite in indexed_suite_to_bin_dir, f"{str(i_suite)} has not been compiled"
    for i_patches, ratio, summary_path in ((perfect_i_patches, init_ratio_perfect, perfect_summary_path),
                                           (fame_i_patches, init_ratio_fame, fame_summary_path)):
        if i_patches is not None:
            try:
                assert 0 <= ratio <= 1, ratio
            except Exception as e:
                assert False, e
            assert os.path.isabs(summary_path), summary_path
            if not dry_run:
                assert not os.path.exists(summary_path), summary_path

    emitter.sub_sub_title("Generating Patches")

    if num_patches_wanted <= 0:
        emitter.normal(f"\t{num_patches_wanted} patches wanted; patch generation skipped")
        return [], []

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    dir_arja = Path(values._dir_root, "extern", "arja").resolve()
    assert os.path.isdir(dir_arja), dir_arja

    if use_arja:
        arja_jar = Path(dir_arja, "target", "Arja-0.0.1-SNAPSHOT-jar-with-dependencies.jar").resolve()
        assert os.path.isfile(arja_jar), arja_jar

        repair_command = f'{java_executable} -cp {str(arja_jar)}  us.msu.cse.repair.Main ArjaE'
    else:
        dir_evosuite = Path(values._dir_root, "extern", "evosuite").resolve()
        assert os.path.isdir(dir_evosuite), dir_evosuite

        evosuite_client_jar = Path(dir_evosuite, "client", "target", "evosuite-client-1.2.0-jar-with-dependencies.jar")
        assert os.path.isfile(evosuite_client_jar), evosuite_client_jar

        repair_command = f'{java_executable} -cp {str(evosuite_client_jar)} org.evosuite.patch.ERepairMain'

        # extensions on top of Arja
        # repair_command += f' -DmutateOperators {"true" if mutate_operators else "false"}'

        if dir_fames is not None:
            repair_command += f' -DfameOutputRoot {str(dir_fames)}'

        if perfect_i_patches is not None:
            summaries = [i_patch.patch.read_summary_file() for i_patch in perfect_i_patches]

            if not dry_run:
                with open(perfect_summary_path, 'w') as f:
                    f.write("\n".join(summaries))

            repair_command += (f' -DperfectPath {str(perfect_summary_path)}'
                               f' -DinitRatioOfPerfect {init_ratio_perfect}'
                               )

        if fame_i_patches is not None:
            summaries = [i_patch.patch.read_summary_file() for i_patch in fame_i_patches]

            if not dry_run:
                with open(fame_summary_path, 'w') as f:
                    f.write("\n".join(summaries))

            repair_command += (f' -DhallOfFameInPath {str(fame_summary_path)}'
                               f' -DinitRatioOfFame {init_ratio_fame}'
                               )

    arja_default_population_size = 40
    max_generations = 2000000  # use a large one to keep ARJA running forever
    # there is `populationSize * maxGenerations` as an `int` in ARJA; do not overflow
    assert arja_default_population_size * max_generations <= 0x7fffffff

    suites_runtime_deps = set()
    for i_suite in indexed_suites:
        suites_runtime_deps.update([str(dep) for dep in i_suite.suite.runtime_deps])

    dependences = ":".join([str(dir_deps), *suites_runtime_deps])

    if not dry_run:
        with open(additional_tests_info_path, 'w') as f:
            f.write("\n".join(
                [f"{i_test.indexed_suite.suite.junit_class}#{i_test.method_name}" for i_test in indexed_tests]))

    if dependences:
        repair_command += f' -Ddependences "{dependences}" '
    repair_command += (
                    f' -DsrcJavaDir "{str(dir_src)}" -DbinJavaDir "{str(dir_bin)}"'
                    f' -DbinTestDir "{str(dir_test_bin)}"'
                    f' -DpatchOutputRoot "{str(dir_patches)}"'
                    f' -DdiffFormat true -DmaxGenerations {max_generations}'
                    f' -DexternalProjRoot {str(dir_arja)}/external'
                    f' -DadditionalTestsInfoPath {str(additional_tests_info_path)}'
                    f' -DwaitTime 30000'
                    f' -DuseD4JInstr false'
                    )

    # -DmaxTime is in minutes; set maxTime to be double timeout_in_seconds to be safe
    max_time = math.ceil(timeout_in_seconds / 60 * 2)
    # maxTime in millisecond is an int in Arja
    assert max_time * 60 * 1000 <= 0x7fffffff
    repair_command += f' -DmaxTime {max_time}'

    # Output directory of ARJA (`patchOutputRoot`) looks like:
    #
    # {patchOutputRoot}/
    # |__ Patch_{n1}.txt
    # |__ Patch_{n2}.txt
    # |
    # |__ Patch_{n1}/
    # |   |__ diff
    # |   |__ patched/
    # |       |__ foo/
    # |       |__ bar/
    # |           |__ Baz.java
    # |
    # |__ Patch_{n2}/
    # |   |__ diff
    # |   |__ patched/
    # ...
    # where {n1}, {n2}, etc. are non-negative integers without leading zeros;
    # Patch_{n1}.txt is ARJA's custom description of the patch;
    # diff is a unified diff file; when applying patch in `srcJavaDir`, strip level is `len(Path(dir_src).parts)`;
    # patched/ holds patched versions of all changed source files, with the original package structure.

    if not dry_run:
        emitter.normal(f"\trunning repair, waiting for {num_patches_wanted} plausible patches")
        emitter.normal(f"\toutput directory: {str(dir_patches)}")

        emitter.command(repair_command)

        # put additional tests in binTestDir
        symlinks = []
        for i_suite in indexed_suites:
            i_test_bin_dir = indexed_suite_to_bin_dir[i_suite]
            class_files = glob.glob(os.path.join(str(i_test_bin_dir), "**", "*.class"), recursive=True)
            for class_file in class_files:
                dst = Path(dir_test_bin, os.path.relpath(class_file, start=i_test_bin_dir))
                assert dst.parent.is_dir(), f"{str(dst.parent)} is not an existing directory"
                assert not dst.exists(), f"{str(dst)} already exists"
                os.symlink(class_file, dst)
                symlinks.append(dst)

        try:
            popen = subprocess.Popen(shlex.split(repair_command), stdout=DEVNULL, stderr=PIPE)

            time_to_stop = time.time() + timeout_in_seconds
            stopped_early = False
            while time.time() < time_to_stop or not timeout_in_seconds:
                return_code = popen.poll()

                # Arja writes the Patch_{n}.txt files lastly. If these are ready, then other patch files must have also
                # been written. So only check these.
                num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])

                if return_code == 0:
                    stopped_early = True
                    emitter.normal(
                        f"\trepair terminated normally after {max_generations} generations; got {num_patches} patches")
                    break
                elif return_code is not None:
                    utilities.error_exit("repair did not exit normally",
                                        popen.stderr.read().decode("utf-8"), f"return code: {return_code}")
                elif num_patches >= num_patches_wanted:
                    stopped_early = True
                    popen.terminate()
                    try:
                        timeout = 10
                        popen.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        utilities.error_exit(
                            f"repair did not terminate within {timeout} seconds after SIGTERM (pid = {popen.pid});"
                            f" repair aborted")
                    emitter.normal(f"\tTerminated repair because there are enough patches; got {num_patches} patches")
                    break
            if not stopped_early:
                popen.terminate()
                try:
                    timeout = 10
                    popen.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    utilities.error_exit(
                        f"repair did not terminate within {timeout} seconds after SIGTERM (pid = {popen.pid});"
                        f" repair aborted")
                num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])
                emitter.normal(f"\trepair stopped due to timeout; got {num_patches} patches")
        finally:
            for symlink in symlinks:
                os.unlink(symlink)
    else:
        num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])
        emitter.normal(f"\tDry run; will reuse the {num_patches} patches in {dir_patches}")

    strip = len(Path(dir_src).parts)

    def read_arja_output_root(output_root):
        result = []

        for entry in os.scandir(output_root):
            if not entry.is_file():
                assert re.fullmatch(r"Patch_\d+", entry.name), entry.path
                continue

            assert re.fullmatch(r"Patch_\d+\.txt", entry.name), entry.path

            directory = Path(entry.path).with_suffix("")
            assert utilities.is_nonempty_dir(directory), str(directory)

            diff_file = Path(directory, "diff")

            patched_dir = Path(directory, "patched")

            changed_files = [Path(x).relative_to(patched_dir) for x in
                             glob.glob(os.path.join(patched_dir, "**", "*.java"), recursive=True)]

            changed_classes = [".".join(file.with_suffix("").parts) for file in changed_files]

            key = directory.name.split("_")[1]

            summary_file = Path(directory, "summary")

            result.append(Patch(diff_file, strip, changed_files, changed_classes, key, summary_file))

        return result

    patches = read_arja_output_root(dir_patches)

    if (dir_fames is not None) and (not use_arja):
        hall_of_fame_patches = read_arja_output_root(dir_fames)
    else:
        hall_of_fame_patches = []

    return patches, hall_of_fame_patches


async def scan_for_tests(dir_bin, dir_test_bin, dir_deps):
    """
    returned dict looks like:
    {"foo.bar.Baz1": ["method01", "method02"], "foo.bar.Baz2": ["method02", "method03"]}
    """
    assert os.path.isabs(dir_bin), dir_bin
    assert os.path.isabs(dir_test_bin), dir_test_bin
    assert os.path.isabs(dir_deps), dir_deps
    assert utilities.is_nonempty_dir(dir_bin), dir_bin
    assert utilities.is_nonempty_dir(dir_test_bin), dir_test_bin
    assert os.path.isdir(dir_deps), dir_deps
    for entry in os.scandir(dir_deps):
        assert entry.name.endswith(".jar"), entry.path

    result = []

    async def suites_scanner_connected(reader, _):
        result.append((await reader.read()).decode("utf-8"))

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    scanner_jar = Path(values._dir_root, "extern", "test-suites-scanner", "target",
                       "test-suites-scanner-1.0-SNAPSHOT-jar-with-dependencies.jar")
    assert scanner_jar.is_file(), str(scanner_jar)

    server_socket = socket.socket()
    server_socket.bind(("localhost", 0))
    _, port = server_socket.getsockname()
    server = await asyncio.start_server(suites_scanner_connected, sock=server_socket)

    dependences = [entry.path for entry in os.scandir(dir_deps)]

    command = (f"{java_executable} -cp {scanner_jar} evorepair.TestSuitesScanner"
               f" {port} {str(dir_bin)} {str(dir_test_bin)} {':'.join(dependences)}"
               )

    async with server:
        await server.start_serving()

        emitter.command(command)

        process = await asyncio.create_subprocess_shell(command, stdout=DEVNULL, stderr=PIPE)
        return_code = await process.wait()
        if return_code != 0:
            stderr = await process.stderr.read()
            utilities.error_exit("TestSuitesScanner did not exit normally", stderr.decode("utf-8"),
                                 f"exit code is {return_code}")

    return json.loads(result[0])
