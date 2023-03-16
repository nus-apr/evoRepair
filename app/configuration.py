import os
import random
import sys
import re
import shutil
import argparse
from pathlib import Path
from app import emitter, logger, values, reader
from app.utilities import error_exit
from datetime import datetime, timezone, timedelta

class Configurations:
    __config_file = None
    __runtime_config_values = {}
    __default_config_values = {
        "depth": 3,
        "iteration-limit": 1,
        "patch-rank-limit": 5,
        "stack-size": 15000,
        "time-duration": 60, # minutes
        "use-cache": False,
        "is-debug": False,
        "dry-run-patch": False,
        "dry-run-test": False
    }

    def read_arg_list(self, arg_list):
        emitter.normal("reading configuration values from arguments")
        if arg_list.debug:
            self.__runtime_config_values["is-debug"] = True
        if arg_list.config:
            self.__config_file = str(arg_list.config)
        if arg_list.cache:
            self.__runtime_config_values["use-cache"] = True
        self.__runtime_config_values["use-hotswap"] = arg_list.use_hotswap
        self.__runtime_config_values["use-arja"] = arg_list.arja
        # self.__runtime_config_values["mutate-operators"] = arg_list.mutate_operators
        # self.__runtime_config_values["mutate-variables"] = arg_list.mutate_variables
        # self.__runtime_config_values["mutate-methods"] = arg_list.mutate_methods
        self.__runtime_config_values["init-ratio-perfect"] = arg_list.init_ratio_perfect
        self.__runtime_config_values["init-ratio-fame"] = arg_list.init_ratio_fame
        self.__runtime_config_values["num-perfect-patches"] = arg_list.num_perfect_patches
        self.__runtime_config_values["patch-gen-timeout"] = arg_list.patch_gen_timeout
        self.__runtime_config_values["test-gen-timeout"] = arg_list.test_gen_timeout
        self.__runtime_config_values["num-iterations"] = arg_list.num_iterations
        self.__runtime_config_values["total-timeout"] = arg_list.total_timeout
        self.__runtime_config_values["dry-run-patch"] = arg_list.dry_run_patch
        self.__runtime_config_values["dry-run-test"] = arg_list.dry_run_test
        self.__runtime_config_values["dir-test"] = arg_list.dir_test
        self.__runtime_config_values["dir-patch"] = arg_list.dir_patch
        self.__runtime_config_values["passing-tests-partitions"] = arg_list.passing_tests_partitions
        self.__runtime_config_values["valid-population-size"] = arg_list.valid_population_size
        self.__runtime_config_values["random-seed"] = arg_list.random_seed
        self.__runtime_config_values["no-change-localization"] = arg_list.no_change_localization
        self.__runtime_config_values["dir-output"] = arg_list.dir_output

    def read_conf_file(self):
        emitter.normal("reading configuration values form configuration file")
        emitter.note("\t[file] " + self.__config_file)
        logger.information(self.__config_file)
        if not os.path.exists(self.__config_file):
            emitter.error("[NOT FOUND] Configuration file " + self.__config_file)
            exit()
        if os.path.getsize(self.__config_file) == 0:
            emitter.error("[EMPTY] Configuration file " + self.__config_file)
            exit()

        config_json = reader.read_json(self.__config_file)
        try:
            self.__runtime_config_values["work-dir"] = os.path.abspath(os.path.dirname(self.__config_file))
            project_info = config_json["project"]
            self.__runtime_config_values["subject"] = project_info["name"]
            self.__runtime_config_values["tag-id"] = project_info["tag"]
            self.__runtime_config_values["src-dir"] = project_info["source-directory"]
            self.__runtime_config_values["test-dir"] = project_info["test-directory"]
            self.__runtime_config_values["deps-dir"] = project_info["deps-directory"]
            self.__runtime_config_values["classes-dir"] = project_info["class-directory"]
            self.__runtime_config_values["source-version"] = project_info.get("source-version", None)

            #localization_info = config_json["localization"]
            #self.__runtime_config_values["fix-locations"] = localization_info["fix-locations"]

            build_info = config_json["build"]
            command_info = build_info["commands"]
            self.__runtime_config_values["build-dir"] = build_info["directory"]
            self.__runtime_config_values["build-cmd"] = command_info["build"]
            self.__runtime_config_values["clean-cmd"] = command_info["clean"]
            self.__runtime_config_values["pre-build-cmd"] = command_info["pre-build"]

        except KeyError as exc:
            raise ValueError(f"missing field in {self.__config_file}: {exc}")

    def print_configuration(self):
        emitter.configuration("log file", values.file_log_main)
        emitter.configuration("output directory", values.dir_output)
        emitter.configuration("working directory", values.dir_exp)
        emitter.configuration("stack size", values.stack_size)
        emitter.configuration("tag id", values.tag_id)
        emitter.configuration("debug mode", values.is_debug)
        emitter.configuration("hotswap", values.use_hotswap)
        emitter.configuration("use arja", values.use_arja)
        # emitter.configuration("mutate operators", values.mutate_operators)
        # emitter.configuration("mutate variables", values.mutate_variables)
        # emitter.configuration("mutate methods", values.mutate_methods)
        emitter.configuration("ratio of perfect patches", values.init_ratio_perfect)
        emitter.configuration("ratio of user-tests-adequate patches", values.init_ratio_fame)
        emitter.configuration("desired number of perfect patches", values.num_perfect_patches)
        emitter.configuration("patch generation timeout", values.patch_gen_timeout)
        emitter.configuration("test generation timeout", values.test_gen_timeout)
        emitter.configuration("number of iterations to run", values.num_iterations)
        emitter.configuration("total timeout", values.total_timeout)
        emitter.configuration("dry run for patch generation", values.dry_run_repair)
        emitter.configuration("dry run for test generation", values.dry_run_test_gen)
        emitter.configuration("number of partitions of passing user test cases", values.passing_tests_partitions)
        emitter.configuration("number of valid patches to generate in each initial iterations",
                              values.valid_population_size)
        emitter.configuration("do not use generated tests for fault localization", values.no_change_localization)
        emitter.configuration("seed of pseudorandom number generator", values.random_seed)

    def get_value(self, config_name):
        condition = config_name in self.__runtime_config_values and self.__runtime_config_values[config_name]
        if condition:
            return self.__runtime_config_values[config_name]
        return self.__default_config_values[config_name]

    def update_configuration(self):
        emitter.normal("updating configuration values")
        values.tag_id = self.__runtime_config_values["tag-id"]
        values.dir_exp = self.__runtime_config_values["work-dir"]
        values.dir_src = self.__runtime_config_values["src-dir"]
        if not os.path.isdir(values.dir_src):
            values.dir_src = values.dir_exp + "/" + values.dir_src

        values.cmd_build = self.__runtime_config_values["build-cmd"]
        values.cmd_clean = self.__runtime_config_values["clean-cmd"]
        values.cmd_pre_build = self.__runtime_config_values["pre-build-cmd"]
        values.is_debug = self.get_value("is-debug")
        values.use_cache = self.get_value("use-cache")
        values.use_hotswap = self.__runtime_config_values["use-hotswap"]
        values.use_arja = self.__runtime_config_values["use-arja"]
        # values.mutate_operators = self.__runtime_config_values["mutate-operators"]
        # values.mutate_variables = self.__runtime_config_values["mutate-variables"]
        # values.mutate_methods = self.__runtime_config_values["mutate-methods"]
        values.init_ratio_perfect = self.__runtime_config_values["init-ratio-perfect"]
        values.init_ratio_fame = self.__runtime_config_values["init-ratio-fame"]
        values.num_perfect_patches = self.__runtime_config_values["num-perfect-patches"]
        values.patch_gen_timeout = self.__runtime_config_values["patch-gen-timeout"]
        values.test_gen_timeout = self.__runtime_config_values["test-gen-timeout"]
        values.num_iterations = self.__runtime_config_values["num-iterations"]
        values.total_timeout = self.__runtime_config_values["total-timeout"]
        if values.total_timeout is not None:
            values.time_system_end = values.time_system_start + values.total_timeout
        else:
            values.time_system_end = None

        values.dry_run_test_gen = self.__runtime_config_values["dry-run-test"]
        values.dry_run_repair = self.__runtime_config_values["dry-run-patch"]
        values.passing_tests_partitions = self.__runtime_config_values["passing-tests-partitions"]
        values.valid_population_size = self.__runtime_config_values["valid-population-size"]
        values.source_version = self.__runtime_config_values["source-version"]
        values.no_change_localization = self.__runtime_config_values["no-change-localization"]
        values.random_seed = self.__runtime_config_values["random-seed"]
        random.seed(values.random_seed)

        subject_id = f"{self.__runtime_config_values['subject']}-{self.__runtime_config_values['tag-id']}"
        # avoid colons in dir names because they disturb classpaths
        time = datetime.now(tz=timezone(offset=timedelta(hours=8))).strftime("%y%m%d_%H%M%S")
        if self.__runtime_config_values['dir-output'] is not None:
            values.dir_output = Path(self.__runtime_config_values['dir-output'])
        else:
            values.dir_output = Path(values.dir_output_base, f"{subject_id}-{time}")
        values.file_oracle_locations = Path(values.dir_output, values.filename_oracle_locations)

        values.dir_log = "/".join([values.dir_log_base, values.tag_id])
        values.stack_size = self.get_value("stack-size")
        sys.setrecursionlimit(values.stack_size)

        # update bug information
        work_dir = self.__runtime_config_values["work-dir"]
        values.dir_info["project"] = work_dir
        values.dir_info["source"] = Path(work_dir, self.__runtime_config_values["src-dir"])
        values.dir_info["classes"] = Path(work_dir, self.__runtime_config_values["classes-dir"])
        values.dir_info["tests"] = Path(work_dir, self.__runtime_config_values["test-dir"])
        if self.__runtime_config_values["deps-dir"]:
            values.dir_info["deps"] = Path(work_dir, self.__runtime_config_values["deps-dir"])
        else:
            values.dir_info["deps"] = None

        if self.__runtime_config_values["dir-patch"]:
            values.dir_info["repair"] = self.__runtime_config_values["dir-patch"]
        else:
            values.dir_info["repair"] = Path(values.dir_output, "repair")
        if self.__runtime_config_values["dir-test"]:
            values.dir_info["test-gen"] = self.__runtime_config_values["dir-test"]
        else:
            values.dir_info["test-gen"] = Path(values.dir_output, "test-gen")

    def prepare_experiment(self):
        if not values.use_cache:
            if os.path.isdir(values.dir_output):
                shutil.rmtree(values.dir_output)
            os.mkdir(values.dir_output)

        if os.path.isdir(values.dir_log):
            shutil.rmtree(values.dir_log)
        os.mkdir(values.dir_log)
