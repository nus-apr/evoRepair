from typing import List

from app import emitter, utilities, values
from app.test_suite import TestSuite
from app.patch import Patch

import os
from os.path import abspath
import datetime
from pathlib import Path


"""
This function implements the developer testing to generate test-diagnostics for the repair 

"""
def generate_test_diagnostic():
    emitter.normal("running developer test-suite")

"""
This is the interface for EvoSuite
# Expected Input
# @arg list_classes: list of fully-qualified target class name for testing (modified/patches classes)
# @arg class_path: absolute path for the target build files
# @arg output_dir: (absolute or relative) path to directory in which EvoSuite will place the tests and reports
# Expected Output
# @output list of test-cases JSON format
"""
def generate_additional_test(patches: List[Patch], output_dir, dry_run=False):
    emitter.sub_sub_title("Generating Test Cases")

    classes = set()
    for p in patches:
        classes.update(p.changed_classes)

    result = []
    for classname in classes:
        result.append(
            generate_tests_for_class(classname, values.dir_info["classes"], Path(output_dir, classname), dry_run)
        )

    return result


def generate_tests_for_class(classname, dir_bin, output_dir, dry_run=False):
    dir_bin = abspath(dir_bin)
    output_dir = abspath(output_dir)

    dir_evosuite = abspath(Path(values._dir_root, "extern", "evosuite"))
    evosuite_version = '1.2.1-SNAPSHOT'
    evosuite_jar_path = abspath(Path(dir_evosuite, "master", "target", f"evosuite-master-{evosuite_version}.jar"))

    emitter.normal(f"\trunning evosuite for {classname}")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    elif os.scandir(output_dir):
        emitter.warning(f"\t\t{output_dir} is not empty; will overwrite")

    generate_command = (f"java -jar {evosuite_jar_path} -class {classname} -projectCP {dir_bin}"
                        f" -base_dir {output_dir} -Dassertions=false"
                        f" -Dsearch_budget=20 -Dstopping_condition=MaxTime"
                        )

    if not dry_run:
        return_code = utilities.execute_command(generate_command)
        if return_code != 0:
            utilities.error_exit(f"FAILED TO GENERATE TEST SUITE FOR CLASS {classname}!!\nExit Code: {return_code}")

    test_src = Path(output_dir, "evosuite-tests").resolve()
    junit_classes = [f"{classname}_ESTest"]
    compile_deps = [evosuite_jar_path]
    evosuite_runtime_path = (f"{dir_evosuite}/master/target/standalone_runtime/"
                             f"target/evosuite-standalone-runtime-{evosuite_version}.jar")
    junit_path = f"{values._dir_root}/extern/arja/extern/lib/junit-4.11.jar"
    runtime_deps = [evosuite_runtime_path, junit_path]

    return TestSuite(test_src, classname, junit_classes, compile_deps, runtime_deps, str(test_src))
