from app import emitter, utilities, values
from app.patch import Patch

import os
from pathlib import Path
import glob
import shutil
import re

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


def generate(dir_src, dir_bin, dir_test_bin, dir_deps, dir_patches, dry_run=False):
    for x in dir_src, dir_bin, dir_test_bin, dir_deps:
        assert os.path.isabs(x), x
        assert utilities.is_nonempty_dir(x), x
    assert os.path.isabs(dir_patches), dir_patches
    assert os.path.isdir(dir_patches), dir_patches
    if not dry_run:
        utilities.check_is_empty_dir(dir_patches)

    emitter.sub_sub_title("Generating Patches")

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    dir_arja = Path(values._dir_root, "extern", "arja").resolve()
    assert os.path.isdir(dir_arja), dir_arja

    arja_jar = Path(dir_arja, "target", "Arja-0.0.1-SNAPSHOT-jar-with-dependencies.jar").resolve()
    assert os.path.isfile(arja_jar), arja_jar

    arja_command = (f'{java_executable} -cp {str(arja_jar)}'
                    f' us.msu.cse.repair.Main Arja'
                    f' -DsrcJavaDir "{str(dir_src)}" -DbinJavaDir "{str(dir_bin)}"'
                    f' -DbinTestDir "{str(dir_test_bin)}" -Ddependences "{str(dir_deps)}"'
                    f' -DpatchOutputRoot "{str(dir_patches)}"'
                    f' -DdiffFormat true -DmaxGenerations 10'
                    f' -DexternalProjRoot {str(dir_arja)}/external'
                    )

    if not dry_run:
        emitter.normal("\trunning ARJA")

        arja_return_code = utilities.execute_command(arja_command)
        if arja_return_code != 0:
            utilities.error_exit("ARJA did not exit normally")

    result = []

    # Output directory of ARJA (`patchOutputRoot`) looks like:
    #
    # {patchOutputRoot}/
    # |__ Patch_{n1}.txt
    # |__ Patch_{n2}.txt
    # |
    # |__ Patch_{n1}/
    # |   |__ diff
    # |   |__ patched/
    # |       |__ foo/
    # |       |__ bar/
    # |           |__ Baz.java
    # |
    # |__ Patch_{n2}/
    # |   |__ diff
    # |   |__ patched/
    # ...
    # where {n1}, {n2}, etc. are non-negative integers without leading zeros;
    # Patch_{n1}.txt is ARJA's custom description of the patch;
    # diff is a unified diff file; when applying patch in `srcJavaDir`, strip level is `len(Path(dir_src).parts)`;
    # patched/ holds patched versions of all changed source files, with the original package structure.

    strip = len(Path(dir_src).parts)

    for entry in os.scandir(dir_patches):
        if not entry.is_dir():
            assert re.fullmatch(r"Patch_\d+.txt", entry.name)
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
