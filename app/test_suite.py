from app import emitter, utilities, values

import os
from pathlib import Path

class TestSuite():
    def __init__(self, dir_src, CUT, junit_classes, compile_deps: list, runtime_deps: list, key):
        self.dir_src = dir_src
        self.junit_classes = junit_classes
        self.compile_deps = compile_deps
        self.runtime_deps = runtime_deps
        assert len(junit_classes) == 1
        self.key = key
        self.CUT = CUT

    def __repr__(self):
        return f"TestSuite[src: {self.dir_src}, junits: {self.junit_classes}]"

    def compile(self, out_dir):
        junit_files = []
        for cls in self.junit_classes:
            filename = f"{cls.replace('.', os.path.sep)}.java"
            path = Path(self.dir_src, filename)
            junit_files.append(os.fspath(path))
        files = " ".join(junit_files)

        deps = ":".join(self.compile_deps)
        classpath = f"{self.dir_src}:{deps}:{values.dir_info['classes']}"

        assert not os.path.exists(out_dir)
        os.makedirs(out_dir)

        compile_command = f'javac -cp "{classpath}" -d {out_dir} {files}'
        return_code = utilities.execute_command(compile_command, True)
        if return_code != 0:
            utilities.error_exit(f"TEST COMPILATION FAILED!!\nExit Code: {return_code}")
