from app import emitter, utilities, definitions, values

"""
This is the function to implement the interface with EvoRepair and ARJA(APR Tool)

Expected Inputs
@arg dir_src : directory of source files
@arg dir_classes: directory of class files
@arg dir_test: directory of test files
@arg dir_deps: directory for dependencies

Expected Output
@output list of patches in JSON format [ 1: { path-file: "//"}]
"""
def generate(dir_src, dir_classes, dir_test, dir_deps, fix_loc):
    dummy_arg_1 = ""
    dummy_arg_2 = ""
    emitter.title("Generating Patches")
    list_patches = []
    # some processing

    # example command generation
    repair_command = "arja --something={} --something2={}".format(dummy_arg_1,
                                                                  dummy_arg_2)

    # invoke command
    utilities.execute_command(repair_command)

    # TODO: Implement process to invoke ARJA and generate patches


    return list_patches

