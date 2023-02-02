import os
import shlex
import shutil
import subprocess

from app import values, emitter, utilities
from pathlib import Path
from subprocess import DEVNULL, PIPE


def extract_oracle_locations():
    dir_oracle_parser = Path(values._dir_root, "extern", "oracle-parser")
    oracle_parser_jar = Path(dir_oracle_parser, "target", "oracle-parser-1.0-SNAPSHOT-jar-with-dependencies.jar")
    assert os.path.isfile(oracle_parser_jar), oracle_parser_jar

    dir_src = Path(values.dir_src)
    dir_output = Path(values.dir_output)

    java_executable = shutil.which("java")
    if java_executable is None:
        raise RuntimeError("Java executable not found")

    oracle_parser_command = f"{java_executable} -jar {str(oracle_parser_jar)} {str(dir_src)} {str(dir_output)} {values.filename_oracle_locations}"
    emitter.normal(f"searching for oracle locations in {dir_src}")

    emitter.command(oracle_parser_command)

    process = subprocess.run(shlex.split(oracle_parser_command), stdout=DEVNULL, stderr=PIPE)

    if process.returncode != 0:
        utilities.error_exit("failed to extract oracle locations", process.stderr.decode("utf-8"),
                             f"exit code: {process.returncode}")
