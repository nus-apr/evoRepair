from app import emitter, utilities, definitions, values

"""
This is the function to implement the interfacing with UniAPR (optimized validation)

Expected Input
@arg list of patches
@arg list of test cases

Expected Output
@output matrix of result for each test x patch
@output sorted list of plausible patches
@output ranked list of test-cases and their mutation score
"""
def validate(list_patches, list_tests):
    plausible_patches = []
    test_scores = dict()
    validation_results = dict()
    emitter.title("Validating Generated Patches")

    # TODO: Implement process to invoke UniAPR and validate patches

    return plausible_patches, test_scores, validation_results



"""
This is the interface for EvoSuite
# Expected Input
# @arg class_name: target class name for testing
# @arg class_path: path for the target build files

# Expected Output
# @output list of test-cases JSON format
"""
def generate_additional_test(class_name, class_path):
    dummy_arg_1 = ""
    emitter.title("Generating Patches")
    list_tests = []
    # some processing

    # example command generation
    generate_command = "evosuite --algorithm={}".format(dummy_arg_1)

    # invoke command
    utilities.execute_command(generate_command)

    # TODO: Implement process to invoke EvoSuite and generate additional test-cases

    return list_tests


