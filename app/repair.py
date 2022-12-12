from app import emitter, utilities, values

from os.path import exists, isdir
import os
import datetime

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
                    f' -DsrcJavaDir "{dir_src}" -DbinJavaDir "{dir_bin}"'
                    f' -DbinTestDir "{dir_test_bin}" -Ddependences "{dir_deps}"'
                    f' -DpatchOutputRoot "{dir_patches}"'
                    f' -DdiffFormat true -DmaxGenerations 10'
                    f' -DexternalProjRoot {dir_arja}/external'
                    )
    arja_return_code = utilities.execute_command(arja_command)

    if arja_return_code != 0:
        emitter.error("\tARJA did not exit normally; no patch generated")
        return []

    if not exists(dir_patches):
        return []

    return [f"{patch.path}/diff" for patch in os.scandir(dir_patches) if patch.is_dir()]

