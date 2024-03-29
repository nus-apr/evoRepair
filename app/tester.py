import re
import time
from typing import List

from app import emitter, utilities, values
from app.test_suite import TestSuite
from app.patch import Patch
from app.test_suite import Test, IndexedTest

import os
from os.path import abspath
import datetime
from pathlib import Path

import xml.etree.ElementTree as ET
import shutil
import subprocess
from subprocess import STDOUT, PIPE
import shlex

from collections import defaultdict
import json

"""
This function implements the developer testing to generate test-diagnostics for the repair 

"""
def generate_test_diagnostic():
    emitter.normal("running developer test-suite")

"""
This is the interface for EvoSuite
# Expected Input
# @arg classname: fully-qualified target class name for testing (modified/patches classes)
# @arg dir_bin: absolute path for the target build files
# @arg output_dir: (absolute or relative) path to directory in which EvoSuite will place the tests and reports
# @arg target_lines_path: path to JSON specifying the patched classes + line numbers
# Expected Output
# @output list of test-cases JSON format
"""
def generate_additional_test(indexed_patches, dir_output, junit_suffix,
                             target_patches_file=None,
                             seed_i_tests=None, seeds_file=None, kill_matrix=None,
                             dry_run=False, timeout_per_class_in_seconds=0, random_seed=0):
    assert os.path.isabs(dir_output)
    assert os.path.isdir(dir_output)
    if not dry_run:
        utilities.check_is_empty_dir(dir_output)
    assert junit_suffix.endswith("Test"), f'junit_suffix "{junit_suffix}" is invalid; must end with "Test"'
    if target_patches_file is not None:
        assert os.path.isabs(target_patches_file), target_patches_file
        if not dry_run:
            assert not os.path.exists(target_patches_file), target_patches_file
    if seed_i_tests is not None:
        assert seeds_file is not None
        assert os.path.isabs(seeds_file), str(seeds_file)
        if not dry_run:
            assert not os.path.exists(seeds_file), str(seeds_file)
        assert kill_matrix is not None

    emitter.sub_sub_title("Generating Test Cases")

    classes = set()
    for x in indexed_patches:
        classes.update(x.patch.changed_classes)

    class_names_with_dollar = [x for x in classes if "$" in classes]
    assert not class_names_with_dollar, class_names_with_dollar

    if target_patches_file is not None:
        target_patches_info = [
            {
                "index": i_patch.get_index_str(),
                "fixLocations": [
                    {
                        "classname": classname,
                        "targetLines": changed_lines
                    }
                    for classname, changed_lines in i_patch.patch.get_fix_locations().items()
                ]
            }
            for i_patch in indexed_patches
        ]

        if not dry_run:
            with open(target_patches_file, 'w') as f:
                json.dump(target_patches_info, f)

    if seed_i_tests is not None:
        i_tests_for_i_suite = defaultdict(list)
        for i_test in seed_i_tests:
            i_tests_for_i_suite[i_test.indexed_suite].append(i_test)

        seeds_info = [
            {
                "serializedSuite": str(i_suite.suite.dump_file),
                "testPrefix": f"{i_suite.suite.junit_class}#",
                "tests": [
                    {
                        "name": i_test.get_index_str(),
                        "kills": [i_patch.get_index_str() for i_patch in kill_matrix[i_test]] if i_test in kill_matrix
                                 else []
                    }
                    for i_test in i_tests
                ]
            }
            for i_suite, i_tests in i_tests_for_i_suite.items()
        ]

        if not dry_run:
            with open(seeds_file, 'w') as f:
                json.dump(seeds_info, f)

    result = []
    while classes:
        classname = classes.pop()
        dir_output_this_class = Path(dir_output, classname)
        os.makedirs(dir_output_this_class, exist_ok=True)
        if not dry_run:
            assert utilities.is_empty_dir(dir_output_this_class)
        if not utilities.timed_out():
            result.extend(
                generate_tests_for_class(classname, values.dir_info["classes"], dir_output_this_class, junit_suffix,
                                        dry_run=dry_run, timeout_in_seconds=timeout_per_class_in_seconds,
                                        seeds_file=seeds_file, target_patches_file=target_patches_file,
                                        random_seed=random_seed)
            )
        else:
            emitter.normal(f"\tskipping test generation for these classes due to global timeout:"
                           f" {', '.join(classes | set([classname]))}")
            break

    return result


def generate_tests_for_class(classname, dir_bin, dir_output, junit_suffix, dry_run=False, target_patches_file=None,
                             seeds_file=None, timeout_in_seconds=0, random_seed=0):
    assert os.path.isabs(dir_bin)
    assert utilities.is_nonempty_dir(dir_bin)
    assert os.path.isabs(dir_output)
    assert os.path.isdir(dir_output)
    if target_patches_file is not None:
        assert os.path.isabs(target_patches_file)
        assert os.path.isfile(target_patches_file)
    if seeds_file is not None:
        assert os.path.isabs(seeds_file), seeds_file
        assert os.path.isfile(seeds_file), seeds_file
    if not dry_run:
        assert utilities.is_empty_dir(dir_output)

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    dir_evosuite = Path(values._dir_root, "extern", "evosuite")
    evosuite_jar = Path(dir_evosuite, "master", "target", f"evosuite-master-{read_evosuite_version()}.jar")
    assert os.path.isfile(evosuite_jar), evosuite_jar

    evosuite_command = (f"{java_executable}"
                        f" -Drandom_seed={random_seed}"
                        f" -Dclient_on_thread=true"
                        f" -jar {str(evosuite_jar)} -class {classname} -projectCP {str(dir_bin)}"
                        f" -base_dir {str(dir_output)} -Dassertions=false -Djunit_suffix={junit_suffix}"
                        )
    if timeout_in_seconds:
        evosuite_command += f" -Dsearch_budget={timeout_in_seconds} -Dstopping_condition=MaxTime"

    if target_patches_file is not None:
        evosuite_command += f" -generateMOSuite -evorepair=testgen"
        evosuite_command += f" -targetPatches {str(target_patches_file)}"

    if seeds_file is not None:
        evosuite_command += f" -seeds {str(seeds_file)}"

    if os.path.isfile(values.file_oracle_locations):
        evosuite_command += f" -oracleLocations {str(values.file_oracle_locations)}"

    dir_test_src = Path(dir_output, "evosuite-tests")

    dump_file = Path(dir_test_src, "dump")

    test_names_file = Path(dir_test_src, "test_names.txt")

    if not dry_run:
        if utilities.timed_out():
            return []

        emitter.normal(f"\trunning evosuite for {classname}")

        popen = subprocess.Popen(shlex.split(evosuite_command), stdout=PIPE, stderr=STDOUT)

        emitter.command(evosuite_command)

        if timeout_in_seconds:
            emitter.normal(f"\t\twaiting for EvoSuite to terminate in {timeout_in_seconds} seconds\t")
        else:
            emitter.normal("\t\twaiting for EvoSuite to terminate automatically")

        # trust EvoSuite always terminates
        try:
            stdout_data, _ = popen.communicate(
                timeout=(values.time_system_end - time.time()) if values.time_system_end is not None else None)
            return_code = popen.poll()
            if return_code != 0:
                utilities.error_exit("EvoSuite did not exit normally",
                                     stdout_data.decode("utf-8"), f"return code: {return_code}")
        except subprocess.TimeoutExpired:
            popen.kill()
            emitter.normal("\t\tkilled EvoSuite due to global timeout")
            stdout_data, _ = popen.communicate()
            emitter.debug(f"EvoSuite output: {stdout_data.decode('utf-8')}")
            return []

        out_file_prefix = str(Path(dir_test_src, *classname.split('.')))
        test_source = f"{out_file_prefix}{junit_suffix}.java"
        test_scaffold = f"{out_file_prefix}{junit_suffix}_scaffolding.java"
        for x in test_source, test_scaffold, dump_file, test_names_file:
            if not os.path.isfile(x):
                emitter.warning(f"EvoSuite exited normally without generating expected file {x}")
                emitter.warning(f"EvoSuite output: {stdout_data.decode('utf-8')}")
                return []

        emitter.normal("\tEvoSuite terminated normally")
    else:
        emitter.normal(f"\tDry run; will reuse tests in {dir_test_src}")

    junit_class = f"{classname}{junit_suffix}"

    with open(test_names_file) as f:
        lines = [line.strip() for line in f]
        test_names = set([line.split("#")[1] for line in lines if line])

    future = "Future<?> future = executor.submit(new Runnable(){"
    pattern = r"public void (test\d+)\(\)"
    with open(test_source) as f:
        lines = f.readlines()
    for idx, line in enumerate(lines):
        if future in line:
            declration = lines[idx - 1]
            test_name = re.search(pattern, declration).group(1)
            test_names.remove(test_name)
            emitter.warning(f"removed test case {junit_class}#{test_name} because it uses Future")

    compile_deps = [evosuite_jar]

    evosuite_runtime_jar = Path(dir_evosuite, "standalone_runtime", "target",
                                f"evosuite-standalone-runtime-{read_evosuite_version()}.jar")
    assert os.path.isfile(evosuite_runtime_jar), evosuite_runtime_jar
    junit_jar = Path(values.file_junit_jar)
    assert os.path.isfile(junit_jar), junit_jar
    runtime_deps = [evosuite_runtime_jar, junit_jar]

    suite = TestSuite(dir_test_src, junit_class, dump_file, test_names, compile_deps, runtime_deps, key=classname)

    return [Test(suite, test_name) for test_name in suite.test_names]


def read_evosuite_version():
    pom_path = Path(values._dir_root, "extern", "evosuite", "pom.xml")
    root = ET.parse(pom_path).getroot()
    xmlns = re.search(r"(\{.*\})project", root.tag).group(1)
    version = root.find(f"{xmlns}version").text
    return version
