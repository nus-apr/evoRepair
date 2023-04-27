#!/usr/bin/env python3

import os
from pathlib import Path
import subprocess
from subprocess import DEVNULL
import shutil
import shlex
import time
from datetime import datetime, timezone, timedelta
import sys


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

TIME_BUDGET = {
    "chart_1_instr": (6720.6, 312),
    "chart_5_instr": (957, 3306),
    "lang_16_instr": (222, 4098),
    "lang_39_instr": (916.8, 2988),
    "lang_45_instr": (507.6, 3816),
    "math_2_instr": (858, 3546),
    "math_49_instr": (1645.2, 3702),
    "math_56_instr": (6765.6, 228),
    "math_65_instr": (5640, 162),
    "math_95_instr": (2245.8, 3882),
    "math_20_instr": (3554.4, 2034),
    "lang_7_instr": (326.4, 4164),
    "lang_43_instr": (3490.2, 1716),
    "lang_46_instr": (720, 4572),
    "lang_51_instr": (109.8, 4476),

    "math_73_instr": (6642, 360),
    "math_50_instr": (6126.6, 444),
    "chart_1_instr": (6720.6, 312),
    "lang_59_instr": (6248.4, 594),
    "math_70_instr": (1838.4, 2628),
    "math_95_instr": (2245.8, 3882)   
}

def command_for_subject(out_dir_base, subject, seed):
    python = shutil.which("python3")
    config_file = Path("d4j-subjects", subject, "config.json")
    time = datetime.now(tz=timezone(offset=timedelta(hours=8))).strftime("%y%m%d_%H%M%S")
    dir_output = Path(SCRIPT_DIR, out_dir_base, f"{subject}-{time}")
    patch_gen_timeout, test_gen_timeout = TIME_BUDGET[subject]
    patch_gen_timeout = int(patch_gen_timeout)
    test_gen_timeout = int(test_gen_timeout)
    command = (f"{python} Repair.py -d --config {str(config_file)} --dir-output {str(dir_output)} --random-seed {seed}"
               f" --patch-gen-timeout {patch_gen_timeout} --test-gen-timeout {test_gen_timeout}"
               f" --num-perfect-patches 10000 --num-iterations 1 --total-timeout=10800"
    )
    # test filtering for time-4, 11, 14 is flaky due to static initialization
    # have to turn off before that is fixed
    if subject.startswith("time"):
        command += " --no-test-filtered"
    return command


def main(*args):
    if not args:
        print(f"Usage: {sys.argv[0]} out_dir_base subject1[,seed1] subject2[,seed2] ...")
        sys.exit(0)

    out_dir_base = args[0]

    task_list = []
    for task in args[1:]:
        tmp = task.split(",")
        subject = tmp[0]
        if len(tmp) == 1:
            seed = 0
        elif len(tmp) == 2:
            seed = int(tmp[1])
        else:
            raise ValueError(f"Unknown task: {task}")
        task_list.append((subject, seed))

    if task_list:
        os.makedirs(out_dir_base, exist_ok=True)
    else:
        sys.exit(0)

    print(f"{len(task_list)} tasks in total: {' '.join([f'{subject},{seed}' for subject, seed in task_list])}")

    n_parallel = 1
    
    popen_for_subject = {}
    while task_list or popen_for_subject:
        poll_for_subject = {subject: popen.poll() for subject, popen in popen_for_subject.items()}

        live_count = 0
        for subject, poll in poll_for_subject.items():
            if poll is None:
                live_count += 1
            else:
                print(f"{'Finished' if poll == 0 else 'Crashed'}: {subject} {poll}")
                popen_for_subject.pop(subject)
        if live_count == n_parallel:
            time.sleep(60)
            continue

        for _ in range(n_parallel - live_count):
            if task_list:
                subject, seed = task_list.pop(0)
                command = command_for_subject(out_dir_base, subject, seed)
                p = subprocess.Popen(shlex.split(command), shell=False, stdout=DEVNULL, stderr=DEVNULL)
                print(f"Launched {subject} (pid={p.pid}): {command}")
                popen_for_subject[subject] = p
                time.sleep(20)
            else:
                print("All subjects lauched; wait for 60s...")
                time.sleep(60)
                break
    print("Done")


if __name__ == '__main__':
    main(*sys.argv[1:])
