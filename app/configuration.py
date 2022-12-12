import os
import sys
import re
import shutil
import argparse
from pathlib import Path
from app import emitter, logger, values, reader
from app.utilities import error_exit

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
        "is-debug": False
    }

    def read_arg_list(self, arg_list):
        emitter.normal("reading configuration values from arguments")
        if arg_list.debug:
            self.__runtime_config_values["is-debug"] = True
        if arg_list.config:
            self.__config_file = str(arg_list.config)
        if arg_list.cache:
            self.__runtime_config_values["use-cache"] = True

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
            self.__runtime_config_values["work-dir"] = os.path.dirname(self.__config_file)
            project_info = config_json["project"]
            self.__runtime_config_values["subject"] = project_info["name"]
            self.__runtime_config_values["tag-id"] = project_info["tag"]
            self.__runtime_config_values["src-dir"] = project_info["source-directory"]
            self.__runtime_config_values["test-dir"] = project_info["test-directory"]
            self.__runtime_config_values["deps-dir"] = project_info["deps-directory"]
            self.__runtime_config_values["classes-dir"] = project_info["class-directory"]

            localization_info = config_json["localization"]
            self.__runtime_config_values["fix-locations"] = localization_info["fix-locations"]

            build_info = config_json["build"]
            command_info = build_info["commands"]
            self.__runtime_config_values["build-dir"] = build_info["directory"]
            self.__runtime_config_values["build-cmd"] = command_info["build"]
            self.__runtime_config_values["clean-cmd"] = command_info["clean"]
            self.__runtime_config_values["pre-build-cmd"] = command_info["pre-build"]

        except KeyError as exc:
            raise ValueError(f"missing field in {self.__config_file}: {exc}")

    def print_configuration(self):
        emitter.configuration("working directory", values.dir_exp)
        emitter.configuration("stack size", values.stack_size)
        emitter.configuration("tag id", values.tag_id)
        emitter.configuration("debug mode", values.is_debug)

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
        values.dir_output = "/".join([values.dir_output_base, values.tag_id])
        values.dir_log = "/".join([values.dir_log_base, values.tag_id])
        values.stack_size = self.get_value("stack-size")
        values.time_duration_total = self.get_value("time-duration")
        values.iteration_limit = self.get_value("iteration-limit")
        sys.setrecursionlimit(values.stack_size)

        # update bug information
        work_dir = self.__runtime_config_values["work-dir"]
        values.dir_info["source"] = Path(work_dir, self.__runtime_config_values["src-dir"])
        values.dir_info["classes"] = Path(work_dir, self.__runtime_config_values["classes-dir"])
        values.dir_info["tests"] = Path(work_dir, self.__runtime_config_values["test-dir"])
        values.dir_info["deps"] = Path(work_dir, self.__runtime_config_values["deps-dir"])
        values.dir_info["patches"] = Path(work_dir, self.__runtime_config_values["work-dir"], "patches")
        values.dir_info["gen-test"] = Path(work_dir, self.__runtime_config_values["work-dir"], "gen-test")

    def prepare_experiment(self):
        if not values.use_cache:
            if os.path.isdir(values.dir_output):
                shutil.rmtree(values.dir_output)
            os.mkdir(values.dir_output)

        if os.path.isdir(values.dir_log):
            shutil.rmtree(values.dir_log)
        os.mkdir(values.dir_log)
