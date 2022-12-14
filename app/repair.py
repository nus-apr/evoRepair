from app import emitter, utilities, values
from app.patch import Patch

from os.path import exists, isdir, abspath
import os
import datetime
from pathlib import Path
import glob

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


def generate(dir_src, dir_bin, dir_test_bin, dir_deps, dir_patches):
    emitter.sub_sub_title("Generating Patches")

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    dir_chart_1_buggy = f"{values._dir_root}/test/chart_1_buggy"

    if exists(dir_patches):
        if not isdir(dir_patches):
            emitter.error(f"{dir_patches} is not a directory")
            return []
        elif os.listdir(dir_patches):
            emitter.warning(f"Output directory {dir_patches} is not empty; patch generation aborted")
            return []

    emitter.normal("\trunning ARJA")
    dir_arja = f"{values._dir_root}/extern/arja"
    arja_command = (f'java -cp {dir_arja}/target/Arja-0.0.1-SNAPSHOT-jar-with-dependencies.jar'
                    f' us.msu.cse.repair.Main Arja'
                    f' -DsrcJavaDir "{abspath(dir_src)}" -DbinJavaDir "{abspath(dir_bin)}"'
                    f' -DbinTestDir "{abspath(dir_test_bin)}" -Ddependences "{abspath(dir_deps)}"'
                    f' -DpatchOutputRoot "{abspath(dir_patches)}"'
                    f' -DdiffFormat true -DmaxGenerations 10'
                    f' -DexternalProjRoot {dir_arja}/external'
                    )
    arja_return_code = utilities.execute_command(arja_command)

    if arja_return_code != 0:
        emitter.error("\tARJA did not exit normally; no patch generated")
        return []

    if not exists(dir_patches):
        return []

    result = []

    path_parts = os.path.normpath(dir_src).split(os.path.sep)
    # empty strings can occur when dir_src has consecutive separators, e.g., "//a/b//c"
    # filter these out
    path_parts = [x for x in path_parts if x]
    strip = len(path_parts) + 1
    for entry in os.scandir(dir_patches):
        if not entry.is_dir():
            continue
        diff_file = Path(entry.path, "diff")
        patched_dir = Path(entry.path, "patched")
        changed_files = glob.glob(os.path.join(patched_dir, "**", "*.java"), recursive=True)
        changed_classes = []
        for file in changed_files:
            path = Path(file).relative_to(patched_dir).with_suffix("")
            changed_classes.append(".".join(path.parts))
        key = Path(entry.path).name.split("_")[1]
        result.append(Patch(diff_file, strip, changed_classes, key))

    return result

