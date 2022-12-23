import re
from typing import List

from app import emitter, utilities, values
from app.test_suite import TestSuite
from app.patch import Patch

import os
from os.path import abspath
import datetime
from pathlib import Path

import xml.etree.ElementTree as ET
import shutil
import subprocess
from subprocess import DEVNULL, PIPE
import shlex

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
def generate_additional_test(patches: List[Patch], dir_output, dry_run=False, timeout_per_class_in_seconds=0):
    assert os.path.isabs(dir_output)
    assert os.path.isdir(dir_output)
    if not dry_run:
        utilities.check_is_empty_dir(dir_output)

    emitter.sub_sub_title("Generating Test Cases")

    classes = set()
    for p in patches:
        classes.update(p.changed_classes)

    class_names_with_dollar = [x for x in classes if "$" in classes]
    assert not class_names_with_dollar, class_names_with_dollar

    result = []
    for classname in classes:
        dir_output_this_class = Path(dir_output, classname)
        os.makedirs(dir_output_this_class, exist_ok=True)
        if not dry_run:
            assert utilities.is_empty_dir(dir_output_this_class)
        result.append(
            generate_tests_for_class(classname, values.dir_info["classes"], dir_output_this_class,
                                     dry_run=dry_run, timeout_in_seconds=timeout_per_class_in_seconds)
        )

    return result


def generate_tests_for_class(classname, dir_bin, dir_output, dry_run=False, fix_location_file=None,
                             timeout_in_seconds=0):
    assert os.path.isabs(dir_bin)
    assert utilities.is_nonempty_dir(dir_bin)
    assert os.path.isabs(dir_output)
    assert os.path.isdir(dir_output)
    if fix_location_file is not None:
        assert os.path.isabs(fix_location_file)
        assert os.path.isfile(fix_location_file)
    if not dry_run:
        assert utilities.is_empty_dir(dir_output)

    emitter.normal(f"\trunning evosuite for {classname}")

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    dir_evosuite = Path(values._dir_root, "extern", "evosuite")
    evosuite_jar = Path(dir_evosuite, "master", "target", f"evosuite-master-{read_evosuite_version()}.jar")
    assert os.path.isfile(evosuite_jar), evosuite_jar

    evosuite_command = (f"{java_executable} -jar {str(evosuite_jar)} -class {classname} -projectCP {str(dir_bin)}"
                        f" -base_dir {str(dir_output)} -Dassertions=false"
                        )
    if timeout_in_seconds:
        evosuite_command += f" -Dsearch_budget={timeout_in_seconds} -Dstopping_condition=MaxTime"

    if fix_location_file is not None:
        evosuite_command += f" -targetLines {str(fix_location_file)}"

    dir_test_src = Path(dir_output, "evosuite-tests")

    if not dry_run:
        popen = subprocess.Popen(shlex.split(evosuite_command), stdout=DEVNULL, stderr=PIPE)

        emitter.command(evosuite_command)

        if timeout_in_seconds:
            emitter.normal(f"\t\twaiting for EvoSuite to terminate in {timeout_in_seconds} seconds\t")
        else:
            emitter.normal("\t\twaiting for EvoSuite to terminate automatically")

        # trust EvoSuite always terminates
        popen.wait()
        return_code = popen.poll()

        if return_code != 0:
            utilities.error_exit("EvoSuite did not exit normally",
                                 popen.stderr.read().decode("utf-8"), f"return code: {return_code}")

        out_file_prefix = str(Path(dir_test_src, *classname.split('.')))
        out1 = f"{out_file_prefix}_ESTest.java"
        out2 = f"{out_file_prefix}_ESTest_scaffolding.java"
        for x in out1, out2:
            if not os.path.isfile(x):
                raise RuntimeError(f"EvoSuite exited normally without generating expected file {x}")

        emitter.normal("\tEvoSuite terminated normally")

    junit_classes = [f"{classname}_ESTest"]

    compile_deps = [evosuite_jar]

    evosuite_runtime_jar = Path(dir_evosuite, "standalone_runtime", "target",
                                f"evosuite-standalone-runtime-{read_evosuite_version()}.jar")
    assert os.path.isfile(evosuite_runtime_jar), evosuite_runtime_jar
    junit_jar = Path(values._dir_root, "extern", "arja", "external", "lib", "junit-4.11.jar")
    assert os.path.isfile(junit_jar), junit_jar
    runtime_deps = [evosuite_runtime_jar, junit_jar]

    return TestSuite(dir_test_src, classname, junit_classes, compile_deps, runtime_deps, str(dir_test_src))


def read_evosuite_version():
    pom_path = Path(values._dir_root, "extern", "evosuite", "pom.xml")
    root = ET.parse(pom_path).getroot()
    xmlns = re.search(r"(\{.*\})project", root.tag).group(1)
    version = root.find(f"{xmlns}version").text
    return version
