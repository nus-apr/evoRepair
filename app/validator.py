from app import emitter, utilities, values
import os

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
    emitter.sub_sub_title("Validating Generated Patches")
    emitter.normal("\trunning UniAPR")
    # TODO: Implement process to invoke UniAPR and validate patches

    return plausible_patches, test_scores, validation_results
