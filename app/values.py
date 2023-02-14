#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os


# ------------------- Configuration Values --------------------
depth = 3
tag_id = ""
dir_exp = ""
dir_src = None
dir_build = None
cmd_build = None
cmd_clean = None
cmd_pre_build = None
config_file = None
iteration_limit = -1
patch_rank_limit = -1
stack_size = 100
time_out = {
    "solver_unsat": None,  # seconds
    "solver_sat": None,  # seconds
    "total": None,  # minutes
}
use_cache = None
is_debug = False
silence_emitter = False
arg_parsed = False
use_hotswap = False
use_arja = False
mutate_operators = False
mutate_variables = False
mutate_methods = False
init_ratio_perfect = 0
init_ratio_fame = 0
num_perfect_patches = 10
patch_gen_timeout = 1200
test_gen_timeout = 60
num_iterations = 0
dry_run_repair = False
dry_run_test_gen = False
junit_version = "4.12"
passing_tests_partitions = 4
valid_population_size = 40
source_version = None

# ------------------- Directories --------------------
_dir_root = "/".join(os.path.realpath(__file__).split("/")[:-2])
dir_log_base = _dir_root + "/logs"
dir_output_base = _dir_root + "/output"
dir_test = _dir_root + "/tests"
dir_output = ""
dir_log = ""
dir_tmp = _dir_root + "/tmp"
dir_backup = _dir_root + "/backup"
dir_tools = _dir_root + "/tools"
dir_data = _dir_root + "/data"

# ------------------- Files --------------------
file_log_main = ""
file_log_error = dir_log_base + "/log-error"
file_log_last = dir_log_base + "/log-latest"
file_log_build = dir_log_base + "/log-build"
file_log_crash = dir_log_base + "/log-crash"
file_log_cmd = dir_log_base + "/log-command"
file_patch_set = ""
file_junit_jar = "/".join([_dir_root, "extern", "arja", "external", "lib", f"junit-{junit_version}.jar"])
file_oracle_locations = ""
filename_oracle_locations = "oracleLocations.json"

# ------------------- Global Values --------------------
tool_name = "EvoRepair"
iteration_no = 0
count_patch_gen = 0
dir_info = dict()

# ------------------- Time Durations --------------------
time_duration_generate = 0
time_duration_explore = 0
time_duration_reduce = 0
time_duration_total = 0
timestamp_check = None

