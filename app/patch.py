from app import values, emitter, utilities, builder

import subprocess
from subprocess import DEVNULL
import shutil
import os
from pathlib import Path
import time

class Patch():
    def __init__(self, diff_file, strip: int, changed_files, changed_classes, key):
        self.diff_file = diff_file
        self.strip = strip
        self.changed_files = changed_files
        self.changed_classes = changed_classes
        self.key = key

    def __repr__(self):
        return f"Patch@{self.key}[diff={self.diff_file}, strip={self.strip}, classes={self.changed_classes}]"

    def compile(self, out_dir):
        assert not os.path.exists(out_dir)

        tmp_dir = Path(values.dir_tmp, f"build_{time.time()}")
        assert not tmp_dir.exists()
        os.makedirs(tmp_dir)

        orig_dir = values.dir_info["project"]
        shutil.copytree(orig_dir, tmp_dir, dirs_exist_ok=True)

        patch_command = f"patch -p{self.strip} < {self.diff_file}"
        relative_dir_src = Path(values.dir_info["source"]).relative_to(orig_dir)
        dir_src = Path(tmp_dir, relative_dir_src)
        process = subprocess.run(patch_command, shell=True, stdout=DEVNULL, stderr=DEVNULL, env=os.environ, cwd=dir_src)
        if process.returncode != 0:
            utilities.error_exit(f"`{patch_command}` in {dir_src} FAIELD!!\nExit Code: {process.returncode}")

        builder.build_project(tmp_dir.as_posix(), values.cmd_build)

        relative_dir_bin = Path(values.dir_info["classes"]).relative_to(orig_dir)
        dir_bin = Path(tmp_dir, relative_dir_bin)
        os.makedirs(out_dir)
        shutil.copytree(dir_bin, out_dir, dirs_exist_ok=True)

        shutil.rmtree(tmp_dir)
