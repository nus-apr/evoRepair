import shlex
import time

from app import emitter, utilities, values
from app.patch import Patch

import os
from pathlib import Path
import glob
import shutil
import re
import subprocess
from subprocess import PIPE, DEVNULL

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


def generate(dir_src, dir_bin, dir_test_bin, dir_deps, dir_patches,
             num_patches_wanted=5, timeout_in_seconds=1200, dry_run=False):
    for x in dir_src, dir_bin, dir_test_bin, dir_deps:
        assert os.path.isabs(x), x
        assert utilities.is_nonempty_dir(x), x
    assert os.path.isabs(dir_patches), dir_patches
    assert os.path.isdir(dir_patches), dir_patches
    if not dry_run:
        utilities.check_is_empty_dir(dir_patches)

    emitter.sub_sub_title("Generating Patches")

    if num_patches_wanted <= 0:
        emitter.normal(f"\t{num_patches_wanted} patches wanted; patch generation skipped")
        return []

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    dir_arja = Path(values._dir_root, "extern", "arja").resolve()
    assert os.path.isdir(dir_arja), dir_arja

    arja_jar = Path(dir_arja, "target", "Arja-0.0.1-SNAPSHOT-jar-with-dependencies.jar").resolve()
    assert os.path.isfile(arja_jar), arja_jar

    arja_default_population_size = 40
    max_generations = 2000000  # use a large one to keep ARJA running forever
    # there is `populationSize * maxGenerations` as an `int` in ARJA; do not overflow
    assert arja_default_population_size * max_generations <= 0x7fffffff
    arja_command = (f'{java_executable} -cp {str(arja_jar)}'
                    f' us.msu.cse.repair.Main Arja'
                    f' -DsrcJavaDir "{str(dir_src)}" -DbinJavaDir "{str(dir_bin)}"'
                    f' -DbinTestDir "{str(dir_test_bin)}" -Ddependences "{str(dir_deps)}"'
                    f' -DpatchOutputRoot "{str(dir_patches)}"'
                    f' -DdiffFormat true -DmaxGenerations {max_generations}'
                    f' -DexternalProjRoot {str(dir_arja)}/external'
                    )

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

    if not dry_run:
        emitter.normal(f"\trunning ARJA, waiting for {num_patches_wanted} plausible patches")
        emitter.normal(f"\toutput directory: {str(dir_patches)}")

        emitter.command(arja_command)
        popen = subprocess.Popen(shlex.split(arja_command), stdout=DEVNULL, stderr=PIPE)

        time_to_stop = time.time() + timeout_in_seconds
        stopped_early = False
        while time.time() < time_to_stop or not timeout_in_seconds:
            return_code = popen.poll()

            # Arja writes the Patch_{n}.txt files lastly. If these are ready, then other patch files must have also
            # been written. So only check these.
            num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])

            if return_code == 0:
                stopped_early = True
                emitter.normal(f"\tARJA terminated normally after {max_generations} generations; got {num_patches} patches")
                break
            elif return_code is not None:
                utilities.error_exit("ARJA did not exit normally",
                                    popen.stderr.read().decode("utf-8"), f"return code: {return_code}")
            elif num_patches >= num_patches_wanted:
                stopped_early = True
                popen.terminate()
                try:
                    timeout = 10
                    popen.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    utilities.error_exit(
                        f"ARJA did not terminate within {timeout} seconds after SIGTERM (pid = {popen.pid});"
                        f" repair aborted")
                emitter.normal(f"\tTerminated ARJA because there are enough patches; got {num_patches} patches")
                break
        if not stopped_early:
            popen.terminate()
            try:
                timeout = 10
                popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                utilities.error_exit(
                    f"ARJA did not terminate within {timeout} seconds after SIGTERM (pid = {popen.pid});"
                    f" repair aborted")
            num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])
            emitter.normal(f"\tARJA stopped due to timeout; got {num_patches} patches")
    else:
        num_patches = len([entry for entry in os.scandir(dir_patches) if entry.is_file()])
        emitter.normal(f"\tDry run; will reuse the {num_patches} patches in {dir_patches}")

    result = []

    strip = len(Path(dir_src).parts)

    for entry in os.scandir(dir_patches):
        if not entry.is_file():
            assert re.fullmatch(r"Patch_\d+", entry.name), entry.path
            continue

        assert re.fullmatch(r"Patch_\d+\.txt", entry.name), entry.path

        directory = Path(entry.path).with_suffix("")
        assert utilities.is_nonempty_dir(directory), str(directory)

        diff_file = Path(directory, "diff")

        patched_dir = Path(directory, "patched")

        changed_files = [Path(x).relative_to(patched_dir) for x in
                         glob.glob(os.path.join(patched_dir, "**", "*.java"), recursive=True)]

        changed_classes = [".".join(file.with_suffix("").parts) for file in changed_files]

        key = directory.name.split("_")[1]

        result.append(Patch(diff_file, strip, changed_files, changed_classes, key))

    return result
