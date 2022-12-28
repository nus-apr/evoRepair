import shlex
import shutil

from app import emitter, utilities, values

import os
from os.path import abspath
from pathlib import Path
import subprocess
from subprocess import DEVNULL, PIPE


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
