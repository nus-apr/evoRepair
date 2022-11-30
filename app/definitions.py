#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os

# ------------------- Directories --------------------

DIRECTORY_ROOT = "/".join(os.path.realpath(__file__).split("/")[:-2])
DIRECTORY_LOG = ""
DIRECTORY_LOG_BASE = DIRECTORY_ROOT + "/logs"
DIRECTORY_TESTS = DIRECTORY_ROOT + "/tests"
DIRECTORY_OUTPUT_BASE = DIRECTORY_ROOT + "/output"
DIRECTORY_OUTPUT = ""
DIRECTORY_TMP = DIRECTORY_ROOT + "/tmp"
DIRECTORY_BACKUP = DIRECTORY_ROOT + "/backup"
DIRECTORY_TOOLS = DIRECTORY_ROOT + "/tools"
DIRECTORY_DATA = DIRECTORY_ROOT + "/data"

# ------------------- Files --------------------

FILE_MAIN_LOG = ""
FILE_ERROR_LOG = DIRECTORY_LOG_BASE + "/log-error"
FILE_LAST_LOG = DIRECTORY_LOG_BASE + "/log-latest"
FILE_MAKE_LOG = DIRECTORY_LOG_BASE + "/log-make"
FILE_CRASH_LOG = DIRECTORY_LOG_BASE + "/log-crash"
FILE_COMMAND_LOG = DIRECTORY_LOG_BASE + "/log-command"
FILE_STANDARD_FUNCTION_LIST = DIRECTORY_DATA + "/standard-function-list"
FILE_STANDARD_MACRO_LIST = DIRECTORY_DATA + "/standard-macro-list"
FILE_PATCH_SET = ""
FILE_PATCH_RANK_MATRIX = ""
FILE_PATCH_RANK_INDEX = ""
FILE_LOCALIZATION_INFO = ""


# ------------------- Configuration --------------------
CONF_DIR_EXPERIMENT = "dir_exp:"
CONF_COMMAND_CONFIG = "config_command:"
CONF_COMMAND_BUILD = "build_command:"
CONF_BINARY_PATH = "binary_path:"
CONF_DIR_SRC = "src_directory:"
CONF_TAG_ID = "tag_id:"
CONF_STATIC = "static:"
CONF_ITERATION_LIMIT = "iterations:"
CONF_STACK_SIZE = "stack_size:"
CONF_RANK_LIMIT = "rank_limit:"


# ----------------- KEY DEFINITIONS -------------------

KEY_DURATION_TOTAL = 'run-time'
KEY_DURATION_BOOTSTRAP = 'bootstrap'
KEY_DURATION_BUILD = "build"
KEY_DURATION_INITIALIZATION = 'initialization'
KEY_DURATION_ANALYSIS = 'analyze'
KEY_DURATION_VERIFY = 'verify'
KEY_DURATION_VALIDATE = 'validate'
KEY_DURATION_LOCALIZATION = 'localization'
KEY_DURATION_REPAIR = "repair"


# ---------------- ARGUMENTS ---------------------------
ARG_CONF_FILE = "--conf="
ARG_DEBUG = "--debug"
ARG_USE_CACHE = "--use-cache"





