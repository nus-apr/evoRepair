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
import random
from app.test_suite import USER_TEST_GENERATION

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

ARJA_ENV = {"TZ": "America/Los_Angeles"}

def generate(dir_src, dir_bin, dir_test_bin, dir_deps, dir_patches,
             basic_i_tests, test_names_path,
             additional_i_tests, additional_tests_info_path,
             mutate_operators=False, mutate_variables=False, mutate_methods=False,
             oracle_locations_file=None,
             num_fames_wanted=0, dir_fames=None,
             perfect_i_patches=None, init_ratio_perfect=None, perfect_summary_path=None,
             fame_i_patches=None, init_ratio_fame=None, fame_summary_path=None,
             num_patches_wanted=5, timeout_in_seconds=1200, dry_run=False,
             use_arja=False, source_version=None, num_patches_forced=0,
             arja_random_seed=0, evo_random_seed=0,
             spectra=None, dir_gzoltar_data=None,
             dir_tmp=None,
             log_file=None
             ):
    for x in dir_src, dir_bin, dir_test_bin:
        assert os.path.isabs(x), x
        assert utilities.is_nonempty_dir(x), x
    if dir_deps:
        assert os.path.isabs(x), x
        assert os.path.isdir(x), x
    assert os.path.isabs(dir_patches), dir_patches
    assert os.path.isdir(dir_patches), dir_patches
    assert os.path.isabs(test_names_path), test_names_path
    assert os.path.isabs(additional_tests_info_path), additional_tests_info_path
    assert os.path.isabs(log_file), log_file
    assert (spectra is None and dir_gzoltar_data is None) or (spectra is not None and dir_gzoltar_data is not None)
    if dir_tmp is not None:
        assert os.path.isabs(dir_tmp), dir_tmp
        assert os.path.isdir(dir_tmp), dir_tmp
    if dir_gzoltar_data is not None:
        assert os.path.isabs(dir_gzoltar_data), dir_gzoltar_data
        if not dry_run:
            assert utilities.is_empty_dir(dir_gzoltar_data), dir_gzoltar_data
        all_test_names = set()
        all_test_names.update([it.get_full_test_name() for it in basic_i_tests])
        all_test_names.update([it.get_full_test_name() for it in additional_i_tests])
        assert all_test_names == set(spectra.test_results.keys())
    if not dry_run:
        utilities.check_is_empty_dir(dir_patches)
        assert Path(dir_patches) not in Path(test_names_path).parents
        assert Path(dir_patches) not in Path(additional_tests_info_path).parents

        if dir_fames is not None:
            utilities.check_is_empty_dir(dir_fames)

        if dir_tmp is not None:
            utilities.check_is_empty_dir(dir_tmp)

        assert not os.path.exists(additional_tests_info_path), additional_tests_info_path

        if log_file is not None:
            assert not os.path.exists(log_file), log_file
    indexed_suites = set()
    indexed_suites.update([it.indexed_suite for it in basic_i_tests if it.indexed_suite.generation != USER_TEST_GENERATION])
    indexed_suites.update([it.indexed_suite for it in additional_i_tests if it.indexed_suite.generation != USER_TEST_GENERATION])
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
    if oracle_locations_file is not None:
        assert os.path.isabs(oracle_locations_file), str(oracle_locations_file)
        assert os.path.isfile(oracle_locations_file), str(oracle_locations_file)

    emitter.sub_sub_title("Generating Patches")

    expecting_fames = dir_fames is not None and not use_arja

    if num_patches_wanted <= 0 and ((not expecting_fames) or num_fames_wanted <= 0):
        msg = f"\t{num_patches_wanted} plausible patches"
        if dir_fames is not None:
            msg += f" and {num_fames_wanted} valid patches"
        msg += " wanted; patch generation skipped"
        emitter.normal(msg)

        return [], [], {}

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    dir_arja = Path(values._dir_root, "extern", "arja").resolve()
    assert os.path.isdir(dir_arja), dir_arja

    arja_jar = Path(dir_arja, "target", "Arja-0.0.1-SNAPSHOT-jar-with-dependencies.jar").resolve()
    assert os.path.isfile(arja_jar), arja_jar

    if dir_tmp is not None:
        tmp_dir_option = f"-Djava.io.tmpdir={str(dir_tmp)}"
    else:
        tmp_dir_option = ""

    if use_arja:
        repair_command = f'{java_executable} {tmp_dir_option} -cp {str(arja_jar)}  us.msu.cse.repair.Main ArjaE'
    else:
        dir_evosuite = Path(values._dir_root, "extern", "evosuite").resolve()
        assert os.path.isdir(dir_evosuite), dir_evosuite

        evosuite_client_jar = Path(dir_evosuite, "client", "target", "evosuite-client-1.2.0-jar-with-dependencies.jar")
        assert os.path.isfile(evosuite_client_jar), evosuite_client_jar

        evosuite_standalone_rt_jar = Path(dir_evosuite, "standalone_runtime", "target",
                                          "evosuite-standalone-runtime-1.2.0.jar")
        assert os.path.isfile(evosuite_standalone_rt_jar), evosuite_standalone_rt_jar

        repair_command = (f'{java_executable}'
                          f' {tmp_dir_option}'
                          f' -Drandom_seed={evo_random_seed}'
                          f' -cp "{str(arja_jar)}:{str(evosuite_client_jar)}:{str(evosuite_standalone_rt_jar)}"'
                          f' org.evosuite.patch.ERepairMain')

        # extensions on top of Arja
        # repair_command += f' -DmutateOperators {"true" if mutate_operators else "false"}'

        if dir_fames is not None:
            repair_command += f' -DfameOutputRoot {str(dir_fames)}'

        if perfect_i_patches is not None:
            summaries = [i_patch.patch.read_summary_file() for i_patch in perfect_i_patches]
            random.shuffle(summaries)

            if not dry_run:
                with open(perfect_summary_path, 'w') as f:
                    f.write("\n".join(summaries))

            repair_command += (f' -DperfectPath {str(perfect_summary_path)}'
                               f' -DinitRatioOfPerfect {init_ratio_perfect}'
                               )

        if fame_i_patches is not None:
            summaries = [i_patch.patch.read_summary_file() for i_patch in fame_i_patches]
            random.shuffle(summaries)

            if not dry_run:
                with open(fame_summary_path, 'w') as f:
                    f.write("\n".join(summaries))

            repair_command += (f' -DhallOfFameInPath {str(fame_summary_path)}'
                               f' -DinitRatioOfFame {init_ratio_fame}'
                               )

    arja_default_population_size = 40
    # use a large one to keep ARJA running forever
    # there is `populationSize * maxGenerations` as an `int` in ARJA; do not overflow
    max_generations = 0x7fffffff // (arja_default_population_size + 1)

    suites_runtime_deps = set()
    for i_suite in indexed_suites:
        suites_runtime_deps.update([str(dep) for dep in i_suite.suite.runtime_deps])


    if not dry_run:
        with open(test_names_path, 'w') as f:
            f.write("\n".join(
                [i_test.get_full_test_name() for i_test in basic_i_tests]))
        with open(additional_tests_info_path, 'w') as f:
            f.write("\n".join(
                [i_test.get_full_test_name() for i_test in additional_i_tests]))

    if dir_deps:
        dependences = ":".join([*[entry.path for entry in os.scandir(dir_deps)], *suites_runtime_deps])
    else:
        dependences = ":".join(suites_runtime_deps)
    repair_command += f' -Ddependences "{dependences}" '

    if source_version:
        repair_command += f' -DsrcVersion {source_version}'

    repair_command += (
                    f' -DsrcJavaDir "{str(dir_src)}" -DbinJavaDir "{str(dir_bin)}"'
                    f' -DbinTestDir "{str(dir_test_bin)}"'
                    f' -DpatchOutputRoot "{str(dir_patches)}"'
                    f' -DdiffFormat true -DmaxGenerations {max_generations}'
                    f' -DexternalProjRoot {str(dir_arja)}/external'
                    f' -DpopulationSize {arja_default_population_size}'
                    f' -DtestNamesPath {str(test_names_path)}'
                    f' -DadditionalTestsInfoPath {str(additional_tests_info_path)}'
                    f' -DwaitTime 30000'
                    f' -DuseD4JInstr false'
                    f' -Dseed {arja_random_seed}'
                    )

    if oracle_locations_file is not None:
        repair_command += f' -DoracleLocationsFile {str(oracle_locations_file)}'

    if dir_gzoltar_data is not None:
        if not dry_run:
            with open(Path(dir_gzoltar_data, "tests"), 'w') as f:
                f.write(spectra.dump_tests_str())
            with open(Path(dir_gzoltar_data, "spectra"), 'w') as f:
                f.write(spectra.dump_susp_values_str())

        repair_command += f' -DgzoltarDataDir {str(dir_gzoltar_data)}'

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
        msg = f"\trunning repair, waiting for {num_patches_wanted} plausible patches"
        if expecting_fames:
            msg += f" and {num_fames_wanted} valid patches"
        emitter.normal("".join(msg))

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
            if log_file is not None:
                repair_log_fp = open(log_file, 'w')
            else:
                repair_log_fp = None
            popen = subprocess.Popen(shlex.split(repair_command), stdout=repair_log_fp, stderr=PIPE,
                                     cwd=values.dir_info["project"], env=ARJA_ENV)

            def terminate_repair(timeout):
                popen.terminate()
                try:
                    popen.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    utilities.error_exit(
                        f"repair did not terminate within {timeout} seconds after SIGTERM (pid = {popen.pid});"
                        f" repair aborted")

            termination_timeout = 10

            time_to_stop = time.time() + timeout_in_seconds
            in_extension = False
            while True:
                return_code = popen.poll()

                # Arja writes the Patch_{n}.txt files lastly. If these are ready, then other patch files must have also
                # been written. So only check these.
                num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])
                num_fames = len([entry for entry in os.scandir(dir_fames) if entry.is_file()])

                patch_count_msg = (f"got {num_patches} plausible patches" +
                                   (f" and {num_fames} valid patches" if expecting_fames else ""))

                if return_code == 0:
                    msg = (f"\trepair terminated normally after {max_generations} generations; {patch_count_msg}")
                    emitter.normal(msg)
                    break
                elif return_code is not None:
                    utilities.error_exit("repair did not exit normally",
                                        popen.stderr.read().decode("utf-8"), f"return code: {return_code}")
                else:
                    if utilities.timed_out():
                        msg = (f"\tstopping repair due to global timeout... {patch_count_msg}")
                        emitter.normal(msg)

                        terminate_repair(termination_timeout)
                        break
                    elif timeout_in_seconds and time.time() >= time_to_stop:
                        if not in_extension:
                            if num_patches >= num_patches_forced:
                                msg = f"\tstopping repair due to timeout... {patch_count_msg}"
                                emitter.normal(msg)

                                terminate_repair(termination_timeout)
                                break
                            emitter.normal(f"\ttime is out but there are only {num_patches} plausible patches;"
                                        f" will wait for {num_patches_forced} plausible patches before exiting")
                            in_extension = True
                        elif num_patches >= num_patches_forced:
                            emitter.normal(
                                f"\treached the minimum requirement of {num_patches_forced} plausible patches; stopping...")

                            terminate_repair(termination_timeout)
                            break
                    elif (num_patches >= num_patches_wanted and
                          ((not expecting_fames) or num_patches + num_fames >= num_patches_wanted + num_fames_wanted)):
                        msg = (f"\tterminating repair because there are enough patches... {patch_count_msg}")
                        emitter.normal(msg)

                        terminate_repair(termination_timeout)
                        break
        finally:
            if repair_log_fp:
                repair_log_fp.close()
            for symlink in symlinks:
                os.unlink(symlink)
    else:
        num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])
        num_fames = len([entry for entry in os.scandir(dir_fames) if entry.is_file()])

        msg = f"\tDry run; will reuse the {num_patches} plausible patches in {str(dir_patches)}"
        if expecting_fames:
            msg += f" and {num_fames} valid patches in {str(dir_fames)}"
        emitter.normal(msg)

    strip = len(Path(dir_src).parts)

    def read_arja_output_root(output_root, has_failed_tests=False):
        patches = []
        failed_test_names = []

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

            patches.append(Patch(diff_file, strip, changed_files, changed_classes, key, summary_file))

            if has_failed_tests:
                failed_tests_file = Path(directory, "failed_tests")
                with open(failed_tests_file) as f:
                    failed_test_names.append([line.strip() for line in f])

        return patches, failed_test_names

    patches, _ = read_arja_output_root(dir_patches, has_failed_tests=False)

    if expecting_fames:
        hall_of_fame_patches, failed_test_names = read_arja_output_root(dir_fames, has_failed_tests=True)

        i_test_for_test_name = {}
        for i_test in basic_i_tests:
            i_test_for_test_name[i_test.get_full_test_name()] = i_test
        for i_test in additional_i_tests:
            i_test_for_test_name[i_test.get_full_test_name()] = i_test

        failed_i_tests = []
        for names in failed_test_names:
            failed_i_tests.append(set([i_test_for_test_name[name] for name in names]))
    else:
        hall_of_fame_patches = []
        failed_i_tests = []

    return patches, hall_of_fame_patches, failed_i_tests


async def scan_for_tests(dir_bin, dir_test_bin, dir_deps, class_names_file):
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

    list_deps = [x for x in os.scandir(dir_deps) if ".jar" in x.name]
    for entry in list_deps:
        assert entry.name.endswith(".jar"), entry.path

    emitter.sub_sub_title("Executing user-provided test cases")

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

    dependences = [entry.path for entry in list_deps]
    deps_str = f'{":".join(dependences)}'

    classpath = f"{str(dir_bin)}:{str(dir_test_bin)}:{deps_str}:{scanner_jar}"

    command = (f'{java_executable} -cp {classpath} evorepair.TestSuitesRunningScanner'
               f' {port} {str(dir_bin)} {str(dir_test_bin)} "{deps_str}" {scanner_jar} {str(class_names_file)}'
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

    test_result = json.loads(result[0])

    return test_result["passingTests"], test_result["failingTests"]


def arja_scan_and_filter_tests(dir_src, dir_bin, dir_test_bin, dir_deps, orig_pos_tests_file, final_tests_file,
                               spectra_file, log_file, source_version=None):
    for x in dir_src, dir_bin, dir_test_bin:
        assert os.path.isabs(x), x
        assert utilities.is_nonempty_dir(x), x
    if dir_deps:
        assert os.path.isabs(dir_deps), dir_deps
        assert os.path.isdir(dir_deps), dir_deps
    for x in orig_pos_tests_file, final_tests_file, spectra_file, log_file:
        assert os.path.isabs(x), x
        assert not os.path.exists(x), x

        java_executable = shutil.which("java")
        if java_executable is None:
            raise RuntimeError("Java executable not found")

        dir_arja = Path(values._dir_root, "extern", "arja").resolve()
        assert os.path.isdir(dir_arja), dir_arja

        arja_jar = Path(dir_arja, "target", "Arja-0.0.1-SNAPSHOT-jar-with-dependencies.jar").resolve()
        assert os.path.isfile(arja_jar), arja_jar

        dir_evosuite = Path(values._dir_root, "extern", "evosuite").resolve()
        assert os.path.isdir(dir_evosuite), dir_evosuite

        evosuite_client_jar = Path(dir_evosuite, "client", "target", "evosuite-client-1.2.0.jar")
        assert os.path.isfile(evosuite_client_jar), evosuite_client_jar

        evosuite_standalone_rt_jar = Path(dir_evosuite, "standalone_runtime", "target",
                                          "evosuite-standalone-runtime-1.2.0.jar")
        assert os.path.isfile(evosuite_standalone_rt_jar), evosuite_standalone_rt_jar

        dummy_dir_patches = values.dir_output

        repair_command = (f'{java_executable}'
                          f' -cp "{str(arja_jar)}:{str(evosuite_client_jar)}:{str(evosuite_standalone_rt_jar)}"'
                          f' org.evosuite.patch.ERepairMain'
                          f' -DsrcJavaDir "{str(dir_src)}" -DbinJavaDir "{str(dir_bin)}"'
                          f' -DbinTestDir "{str(dir_test_bin)}"'
                          f' -DpatchOutputRoot "{str(dummy_dir_patches)}"'
                          f' -DexternalProjRoot {str(dir_arja)}/external'
                          f' -DorgPosTestsInfoPath {str(orig_pos_tests_file)}'
                          f' -DfinalTestsInfoPath {str(final_tests_file)}'
                          f' -DspectraOnly true'
                          f' -DspectraPath {spectra_file}'
                          )
        if dir_deps:
            dependences = ":".join([entry.path for entry in os.scandir(dir_deps)])
        else:
            dependences = ""
        repair_command += f' -Ddependences "{dependences}"'

        if source_version:
            repair_command += f' -DsrcVersion {source_version}'

        emitter.command(repair_command)
        with open(log_file, 'w') as f:
            process = subprocess.run(shlex.split(repair_command), stdout=f, stderr=PIPE, cwd=values.dir_info["project"],
                                     env=ARJA_ENV)
        if process.returncode != 0:
            utilities.error_exit("test scanning did not exit normally",
                                 process.stderr.decode("utf-8"), f"return code: {process.returncode}")
        if not os.path.isfile(spectra_file):
            utilities.error_exit(f"test scanning exited normally without generating expected file {str(spectra_file)}",
                                    f" see logs in {str(log_file)}")

        passing_tests = set()
        failing_tests = set()
        with open(spectra_file) as f:
            for line in f:
                test, result = line.strip().split(",")[:2]
                if result == "PASS":
                    passing_tests.add(test)
                elif result == "FAIL":
                    failing_tests.add(test)
                else:
                    raise Exception(f"Unknown result: {result}")
        return passing_tests, failing_tests


def arja_get_tests_spectra(dir_src, dir_bin, dir_test_bin, dir_deps, i_tests, test_names_path,
                           spectra_file, log_file, source_version=None):
    for x in dir_src, dir_bin, dir_test_bin:
        assert os.path.isabs(x), x
        assert utilities.is_nonempty_dir(x), x
    if dir_deps:
        assert os.path.isabs(dir_deps), dir_deps
        assert os.path.isdir(dir_deps), dir_deps
    for x in test_names_path, spectra_file, log_file:
        assert os.path.isabs(x), x
        assert not os.path.exists(x), x
    indexed_suites = set([it.indexed_suite for it in i_tests if it.indexed_suite.generation != USER_TEST_GENERATION])
    for i_suite in indexed_suites:
        assert i_suite in indexed_suite_to_bin_dir, f"{str(i_suite)} has not been compiled"

    suites_runtime_deps = set()
    for i_suite in indexed_suites:
        suites_runtime_deps.update([str(dep) for dep in i_suite.suite.runtime_deps])

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    dir_arja = Path(values._dir_root, "extern", "arja").resolve()
    assert os.path.isdir(dir_arja), dir_arja

    arja_jar = Path(dir_arja, "target", "Arja-0.0.1-SNAPSHOT-jar-with-dependencies.jar").resolve()
    assert os.path.isfile(arja_jar), arja_jar

    dir_evosuite = Path(values._dir_root, "extern", "evosuite").resolve()
    assert os.path.isdir(dir_evosuite), dir_evosuite

    evosuite_client_jar = Path(dir_evosuite, "client", "target", "evosuite-client-1.2.0.jar")
    assert os.path.isfile(evosuite_client_jar), evosuite_client_jar

    evosuite_standalone_rt_jar = Path(dir_evosuite, "standalone_runtime", "target",
                                        "evosuite-standalone-runtime-1.2.0.jar")
    assert os.path.isfile(evosuite_standalone_rt_jar), evosuite_standalone_rt_jar

    dummy_dir_patches = values.dir_output

    with open(test_names_path, 'w') as f:
        f.write("\n".join(
            [i_test.get_full_test_name() for i_test in i_tests]))

    repair_command = (f'{java_executable}'
                        f' -cp "{str(arja_jar)}:{str(evosuite_client_jar)}:{str(evosuite_standalone_rt_jar)}"'
                        f' org.evosuite.patch.ERepairMain'
                        f' -DsrcJavaDir "{str(dir_src)}" -DbinJavaDir "{str(dir_bin)}"'
                        f' -DbinTestDir "{str(dir_test_bin)}"'
                        f' -DpatchOutputRoot "{str(dummy_dir_patches)}"'
                        f' -DexternalProjRoot {str(dir_arja)}/external'
                        f' -DtestNamesPath {str(test_names_path)}'
                        f' -DspectraPath {spectra_file}'
                        f' -DspectraOnly true'
                        )
    if dir_deps:
        dependences = ":".join([*[entry.path for entry in os.scandir(dir_deps)], *suites_runtime_deps])
    else:
        dependences = ":".join(suites_runtime_deps)
    repair_command += f' -Ddependences "{dependences}"'

    if source_version:
        repair_command += f' -DsrcVersion {source_version}'

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
        with open(log_file, 'w') as f:
            emitter.command(repair_command)
            process = subprocess.run(shlex.split(repair_command), stdout=f, stderr=PIPE, cwd=values.dir_info["project"],
                                     env=ARJA_ENV)
        if process.returncode != 0:
            utilities.error_exit("spectra retrieval did not exit normally",
                                    process.stderr.decode("utf-8"), f"return code: {process.returncode}")
        if not os.path.isfile(spectra_file):
            utilities.error_exit(f"spectra retrieval exited normally without generating expected file {str(x)}",
                                    f" see logs in {str(log_file)}")
    finally:
        for symlink in symlinks:
            os.unlink(symlink)
