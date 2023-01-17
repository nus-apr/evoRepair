from app import values, emitter, utilities, builder

import subprocess
from subprocess import DEVNULL, PIPE
import shutil
import os
from pathlib import Path
import time
from collections import namedtuple
from unidiff import PatchSet


class Patch:
    def __init__(self, diff_file, strip: int, changed_files, changed_classes, key, summary_file):
        self.diff_file = diff_file
        self.strip = strip
        self.changed_files = changed_files
        self.changed_classes = changed_classes
        self.key = key
        self.summary_file = summary_file
        self.__summary = None

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

        patch_command = f"{patch_executable} -p{self.strip} --binary < {self.diff_file}"
        patched_dir_src = Path(tmp_dir, os.path.relpath(values.dir_info["source"], start=dir_project))

        emitter.command(patch_command)
        process = subprocess.run(patch_command, shell=True, stdout=DEVNULL, stderr=PIPE,
                                 cwd=patched_dir_src)
        if process.returncode != 0:
            # transform encoding to dos from unix
            transform_command = f"unix2dos {self.diff_file}"
            utilities.execute_command(transform_command)
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

    def get_fix_locations(self):
        """

        :return: map from full class name to list of changed line numbers (int)

        {
            "foo.bar.Baz1": [2, 3],
            "foo.bar.Baz2": [101, 500, 933]
        }
        """
        result = {}

        with open(self.diff_file) as f:
            diff = f.read()

        patch_set = PatchSet.from_string(diff)
        for patched_file in patch_set:
            assert values.dir_info["source"] in Path(patched_file.source_file).parents
            relative_path = Path(patched_file.source_file).relative_to(values.dir_info["source"])
            classname = ".".join(relative_path.with_suffix("").parts)

            changed_lines = []
            for hunk in patched_file:
                i = 0
                num_lines = len(hunk)
                last_line = None
                while i < num_lines:
                    line = hunk[i]
                    if line.is_removed:
                        assert not last_line.is_added
                        if last_line.is_context:
                            changed_lines.append(line.source_line_no)
                    elif line.is_added:
                        if last_line.is_context:
                            changed_lines.append(last_line.source_line_no + 1)
                    elif line.is_context:
                        pass
                    else:
                        assert not line.value.strip(), line
                    last_line = line
                    i += 1

            result[classname] = changed_lines
        return result

    def read_summary_file(self):
        if self.__summary is None:
            with open(self.summary_file) as f:
                self.__summary = f.read().strip()
        return self.__summary


PatchIndex = namedtuple("PatchIndex", ["generation", "key"])


class IndexedPatch:
    def __init__(self, generation, patch):
        self.generation = generation
        self.patch = patch

    def __hash__(self):
        return hash((self.generation, self.patch.key))

    def __eq__(self, other):
        if not isinstance(other, IndexedPatch):
            return False
        return self.generation == other.generation and self.patch.key == other.patch.key

    def __str__(self):
        return f"{str(self.patch)}@gen{self.generation}"

    def get_index(self):
        return PatchIndex(self.generation, self.patch.key)

    def get_index_str(self):
        return f"{self.patch.key}@gen{self.generation}"
