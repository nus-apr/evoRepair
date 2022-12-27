from app import values, emitter, utilities, builder

import subprocess
from subprocess import DEVNULL, PIPE
import shutil
import os
from pathlib import Path
import time
from collections import namedtuple


class Patch:
    def __init__(self, diff_file, strip: int, changed_files, changed_classes, key):
        self.diff_file = diff_file
        self.strip = strip
        self.changed_files = changed_files
        self.changed_classes = changed_classes
        self.key = key

    def __repr__(self):
        return f"Patch@{self.key}[diff={self.diff_file}, strip={self.strip}, classes={self.changed_classes}]"

    def compile(self, out_dir, changed_only=True):
        assert os.path.isabs(out_dir), out_dir
        assert utilities.is_empty_dir(out_dir), out_dir

        while True:
            tmp_dir = Path(values.dir_tmp, f"patch_compile_{time.time()}")
            if not tmp_dir.exists():
                break
        os.makedirs(tmp_dir)

        dir_project = values.dir_info["project"]
        shutil.copytree(dir_project, tmp_dir, dirs_exist_ok=True)

        patch_executable = shutil.which("patch")
        if patch_executable is None:
            raise RuntimeError('"patch" utility not found')

        patch_command = f"{patch_executable} -p{self.strip} < {self.diff_file}"

        patched_dir_src = Path(tmp_dir, os.path.relpath(values.dir_info["source"], start=dir_project))

        emitter.command(patch_command)
        process = subprocess.run(patch_command, shell=True, stdout=DEVNULL, stderr=PIPE,
                                 cwd=patched_dir_src)
        if process.returncode != 0:
            utilities.error_exit(f"executing `{patch_command}` in {patched_dir_src} failed",
                                 process.stderr.decode("utf-8"),
                                 f"exit code: {process.returncode}")

        builder.build_project(str(tmp_dir), values.cmd_build)

        patched_dir_bin = Path(tmp_dir, os.path.relpath(values.dir_info["classes"], start=dir_project))

        if changed_only:
            changed_class_files = [Path(x).with_suffix(".class") for x in self.changed_files]
            for x in changed_class_files:
                copy_src = Path(patched_dir_bin, x)
                assert copy_src.is_file(), str(copy_src)

                copy_dst = Path(out_dir, x)
                os.makedirs(copy_dst.parent, exist_ok=True)

                shutil.copy2(copy_src, copy_dst)
        else:
            shutil.copytree(patched_dir_bin, out_dir, dirs_exist_ok=True)

        shutil.rmtree(tmp_dir)


PatchIndex = namedtuple("PatchIndex", ["generation", "key"])


class IndexedPatch:
    def __init__(self, generation, patch):
        self.generation = generation
        self.patch = patch

    def __hash__(self):
        return hash((self.generation, self.patch.key))

    def __eq__(self, other):
        if type(other) != IndexedPatch:
            return False
        return self.generation == other.generation and self.patch.key == other.patch.key

    def __str__(self):
        return f"{str(self.patch)}@gen{self.generation}"

    def get_index(self):
        return PatchIndex(self.generation, self.patch.key)
