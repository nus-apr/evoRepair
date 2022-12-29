import shlex
import shutil

from app import emitter, utilities, values

import os
from os.path import abspath
from pathlib import Path
import subprocess
from subprocess import DEVNULL, PIPE
from collections import namedtuple


class TestSuite:
    def __init__(self, dir_src, CUT, junit_class, compile_deps: list, runtime_deps: list, key):
        self.dir_src = dir_src
        self.junit_class = junit_class
        self.compile_deps = compile_deps
        self.runtime_deps = runtime_deps
        self.key = key
        self.CUT = CUT

    def __repr__(self):
        return f"TestSuite[{self.junit_class}@{self.dir_src}]"

    def compile(self, out_dir):
        assert os.path.isabs(out_dir), out_dir
        assert os.path.isdir(out_dir), out_dir

        junit_file = os.path.join(self.dir_src, f"{self.junit_class.replace('.', os.path.sep)}.java")

        class_file = Path(junit_file).with_suffix(".class")
        assert not class_file.exists(), f"{str(class_file)} already exists; compilation aborted"

        javac_executable = shutil.which("javac")
        if javac_executable is None:
            raise RuntimeError("javac executable not found")

        deps = ":".join((str(x) for x in self.compile_deps))
        classpath = f"{str(self.dir_src)}:{deps}:{str(values.dir_info['classes'])}"

        compile_command = f'{javac_executable} -cp "{classpath}" -d {out_dir} {junit_file}'

        emitter.command(compile_command)

        process = subprocess.run(shlex.split(compile_command), stdout=DEVNULL, stderr=PIPE)

        if process.returncode != 0:
            utilities.error_exit("failed to compiled test suite", process.stderr.decode("utf-8"),
                                 f"exit code: {process.returncode}")


class Test:
    def __init__(self, suite, method_name):
        self.suite = suite
        self.method_name = method_name


SuiteIndex = namedtuple("SuiteIndex", ["generation", "key"])


class IndexedSuite:
    def __init__(self, generation, suite):
        self.generation = generation
        self.suite = suite

    def __hash__(self):
        return hash(self.get_index())

    def __eq__(self, other):
        if not isinstance(other, IndexedSuite):
            return False
        return self.get_index() == other.get_index()

    def __str__(self):
        return f"IndexedSuite[{self.suite.key}@gen{self.generation}]"

    def get_index(self):
        return SuiteIndex(self.generation, self.suite.key)


TestIndex = namedtuple("TestIndex", ["generation", "suite_key", "method_name"])


class IndexedTest:
    def __init__(self, generation, test):
        self.indexed_suite = IndexedSuite(generation, test.suite)
        self.method_name = test.method_name

    def __hash__(self):
        return hash(self.get_index())

    def __eq__(self, other):
        if not isinstance(other, IndexedTest):
            return False
        return self.get_index() == other.get_index()

    def __str__(self):
        return f"{self.method_name}@{str(self.indexed_suite)}"

    def get_index(self):
        return TestIndex(*self.indexed_suite.get_index(), self.method_name)

    def get_suite_index(self):
        return self.indexed_suite.get_index()
