from app import emitter, utilities, values

import shlex
import os
from pathlib import Path
import time
import subprocess
from subprocess import PIPE
import textwrap

"""
This is the function to implement the interfacing with UniAPR (optimized validation)

Expected Input
@arg list of patches
@arg list of test cases

Expected Output
@output matrix of result for each test x patch
@output sorted list of plausible patches
@output ranked list of test-cases and their mutation score
"""
def validate(patches, tests):
    emitter.sub_sub_title("Validating Generated Patches")
    emitter.normal("\trunning UniAPR")

    out_dir = Path(values.dir_tmp, f"{time.time()}")
    assert not out_dir.exists()

    patch_bin_dir = Path(out_dir, "patches_bin")
    for p in patches:
        p.compile(Path(patch_bin_dir, p.key))

    test_bin_dir = Path(out_dir, "target", "test-classes")  # UniAPR accepts maven directory structure
    for t in tests:
        t.compile(test_bin_dir)

    write_uniapr_pom(out_dir)

    uniapr_command = f"mvn org.uniapr:uniapr-plugin:validate -DresetJVM=true -DpatchesPool={patch_bin_dir}"

    emitter.command(uniapr_command)

    process = subprocess.run(shlex.split(uniapr_command), stdout=PIPE, stderr=PIPE, env=os.environ, cwd=out_dir)
    if process.returncode != 0:
        utilities.error_exit(f"UniAPR EXECUTION FAILED!!\nExit Code: {process.returncode}")

    failed_patches = parse_uniapr_output(process.stdout.decode("utf-8"))

    return failed_patches


def write_uniapr_pom(out_dir):
    s = textwrap.dedent("""\
        <project>
            <modelVersion>4.0.0</modelVersion>
            <groupId>foo</groupId>
            <artifactId>bar</artifactId>
            <version>baz</version>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.uniapr</groupId>
                        <artifactId>uniapr-plugin</artifactId>
                        <version>1.0-SNAPSHOT</version>
                    </plugin>
                </plugins>
            </build>
        </project>
    """)
    with open(Path(out_dir, "pom.xml"), 'w') as f:
        f.write(s)


def parse_uniapr_output(out):
    return []