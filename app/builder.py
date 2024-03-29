#! /usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import sys
from app.utilities import execute_command, error_exit
from app import values, emitter, reader


def config_project(project_path, custom_config_command=None):
    emitter.normal("configuring program")
    dir_command = "cd {};".format(project_path)
    config_command = custom_config_command
    config_command = dir_command + config_command
    ret_code = execute_command(config_command)
    if int(ret_code) != 0:
        emitter.error(config_command)
        error_exit("CONFIGURATION FAILED!!\nExit Code: " + str(ret_code))


def build_project(project_path, build_command=None):
    dir_command = "cd " + project_path + ";"

    build_command = dir_command + build_command
    build_command = build_command + " > " + values.file_log_build
    ret_code = execute_command(build_command)
    if int(ret_code) != 0:
        emitter.error(build_command)
        error_exit("BUILD FAILED!!\nExit Code: " + str(ret_code))


def soft_restore_project(project_path):
    restore_command = "cd " + project_path + ";"
    if os.path.exists(project_path + "/.git"):
        restore_command += "git reset --hard HEAD"
    elif os.path.exists(project_path + "/.svn"):
        restore_command += "svn revert -R .; "
    elif os.path.exists(project_path + "/.hg"):
        restore_command += "hg update --clean"
    else:
        return
    # print(restore_command)
    execute_command(restore_command)


def clean_project(project_path, binary_path):
    emitter.normal("cleaning files")
    clean_command = f"cd {project_path}; {values.cmd_clean}; exit 0"
    execute_command(clean_command)
