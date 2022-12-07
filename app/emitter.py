# -*- coding: utf-8 -*-

import sys
import os
from app import values, logger
import textwrap
import pty

rows, columns = 600,600
res = os.popen('stty size', 'r').read().split()
if res:
    rows, columns = res

GREY = '\t\x1b[1;30m'
RED = '\t\x1b[1;31m'
GREEN = '\x1b[1;32m'
YELLOW = '\t\x1b[1;33m'
BLUE = '\t\x1b[1;34m'
ROSE = '\t\x1b[1;35m'
CYAN = '\x1b[1;36m'
WHITE = '\t\x1b[1;37m'

PROG_OUTPUT_COLOR = '\t\x1b[0;30;47m'
STAT_COLOR = '\t\x1b[0;32;47m'


def write(print_message, print_color, new_line=True, prefix=None, indent_level=0):
    if not values.silence_emitter:
        message = "\033[K" + print_color + str(print_message) + '\x1b[0m'
        if prefix:
            prefix = "\033[K" + print_color + str(prefix) + '\x1b[0m'
            len_prefix = ((indent_level+1) * 4) + len(prefix)
            wrapper = textwrap.TextWrapper(initial_indent=prefix, subsequent_indent=' '*len_prefix, width=int(columns))
            message = wrapper.fill(message)
        sys.stdout.write(message)
        if new_line:
            r = "\n"
            sys.stdout.write("\n")
        else:
            r = "\033[K\r"
            sys.stdout.write(r)
        sys.stdout.flush()


def header(text):
    write("\n" + "="*100 + "\n\n\t" + text + "\n" + "="*100+"\n", CYAN)
    logger.information(text)


def title(text):
    write("\n\n\t" + text + "\n" + "="*100+"\n", CYAN)
    logger.information(text)


def sub_title(text):
    write("\n\t" + text + "\n\t" + "_"*90+"\n", CYAN)
    logger.information(text)


def sub_sub_title(text):
    write("\n\t\t" + text + "\n\t\t" + "-"*90+"\n", CYAN)
    logger.information(text)


def command(text):
    if values.is_debug:
        prefix = "\t\t[command] "
        write(text, ROSE, prefix=prefix, indent_level=2)
    logger.command(text)


def debug(text):
    if values.is_debug:
        prefix = "\t\t[debug] "
        write(text, GREY, prefix=prefix, indent_level=2)
    logger.debug(text)


def data(text, info=None):
    if values.is_debug:
        prefix = "\t\t[data] "
        write(text, GREY, prefix=prefix, indent_level=2)
        if info:
            write(info, GREY, prefix=prefix, indent_level=2)
    logger.data(text, info)


def normal(text, jump_line=True):
    write(text, BLUE, jump_line)
    logger.output(text)


def highlight(text, jump_line=True):
    indent_length = text.count("\t")
    prefix = "\t" * indent_length
    text = text.replace("\t", "")
    write(text, WHITE, jump_line, indent_level=indent_length, prefix=prefix)
    logger.note(text)


def information(text, jump_line=True):
    write(text, WHITE, jump_line)
    logger.information(text)


def statistics(text):
    write(text, WHITE)
    logger.output(text)


def error(text):
    write(text, RED)
    logger.error(text)


def success(text):
    write(text, GREEN)
    logger.output(text)


def special(text):
    write(text, ROSE)
    logger.note(text)


def program_output(output_message):
    write("\t\tProgram Output:", WHITE)
    if type(output_message) == list:
        for line in output_message:
            write("\t\t\t" + line.strip(), PROG_OUTPUT_COLOR)
    else:
        write("\t\t\t" + output_message, PROG_OUTPUT_COLOR)

def warning(text):
    write(text, YELLOW)
    logger.warning(text)


def note(text):
    write(text, WHITE)
    logger.note(text)


def configuration(setting, value):
    message = "\t[config] " + setting + ": " + str(value)
    write(message, WHITE, True)
    logger.configuration(setting + ":" + str(value))


def end(time_info, is_error=False):
    if values.arg_parsed:
        statistics("\nRun time statistics:\n-----------------------\n")
        statistics("Startup: " + str(time_info["initialization"].format()) + " minutes")
        statistics("Build: " + str(time_info["build"]) + " minutes")
        statistics("Testing: " + str(time_info["testing"]) + " minutes")
        statistics("Localization: " + str(time_info["localization"]) + " minutes")
        statistics("Patch Generation: " + str(time_info["patch-generation"]) + " minutes")
        statistics("Test Generation: " + str(time_info["test-generation"]) + " minutes")
        statistics("Validation: " + str(time_info["validation"]) + " minutes")

        if is_error:
            error("\n" + values.tool_name + " exited with an error after " + time_info[
                values.time_duration_total] + " minutes \n")
        else:
            success("\n" + values.tool_name + " finished successfully after " + time_info[
                values.time_duration_total] + " minutes \n")
