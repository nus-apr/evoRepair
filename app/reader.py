import json
import pickle
import os
import io


def read_json(file_path):
    json_data = None
    if os.path.isfile(file_path):
        with open(file_path, 'r') as in_file:
            content = in_file.read()
            json_data = json.loads(content)
    return json_data


def read_pickle(file_path):
    pickle_object = None
    if os.path.isfile(file_path):
        with open(file_path, 'rb') as pickle_file:
            pickle_object = pickle.load(pickle_file)
    return pickle_object


def read_ast_tree(json_file):
    with io.open(json_file, 'r', encoding='utf8', errors="ignore") as f:
        ast_json = json.loads(f.read())
    return ast_json


def read_compile_commands(database_path):
    command_list = read_json(database_path)
    compile_command_info = dict()
    for entry in command_list:
        file_name = entry["file"]
        dir_path = entry["directory"]
        file_path = dir_path + "/" + file_name
        compile_command_info[file_path] = list()
        argument_list = entry["arguments"]
        for argument in argument_list:
            if "-I" in argument:
                include_rel_path = argument.replace("-I", "")
                count_traverse = str(include_rel_path).count("..")
                include_path = "/".join(dir_path.split("/")[:-count_traverse] + include_rel_path.split("/")[count_traverse:])
                compile_command_info[file_path].append(include_path)
    return compile_command_info

