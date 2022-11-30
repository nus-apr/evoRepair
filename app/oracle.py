import os
from app import definitions, values, emitter, extractor, logger, utilities
from pysmt.shortcuts import is_sat, Not, And, is_unsat
from pysmt.smtlib.parser import SmtLibParser
from six.moves import cStringIO
import numpy as np
from sympy import sympify
from subprocess import Popen, PIPE


tautology_included = False
contradiction_included = False


def update_tautology_included(lock):
    global tautology_included
    res = False
    lock.acquire()
    if not tautology_included:
        tautology_included = True
        res = True
    lock.release()
    return res


def update_contradiction_included(lock):
    global contradiction_included
    res = False
    lock.acquire()
    if not contradiction_included:
        contradiction_included = True
        res = True
    lock.release()
    return res



import sys
if not sys.warnoptions:
    import warnings
    warnings.simplefilter("ignore")


def is_valid_range(check_range):
    lower_bound, upper_bound = check_range
    if lower_bound <= upper_bound:
        return True
    return False


def is_component_constant(patch_comp):
    (cid, semantics), children = patch_comp
    if "constant" in cid:
        return True
    return False


def is_same_children(patch_comp):
    (_, _), children = patch_comp
    right_child = children['right']
    left_child = children['left']
    (cid_right, _), _ = right_child
    (cid_left, _), _ = left_child
    if cid_left == cid_right:
        return True
    return False


def is_always_true(patch):
    program = patch[list(patch.keys())[0]]
    tree, _ = program
    (cid, semantics), children = tree
    if cid not in ["equal", "greater-or-equal", "less-or-equal"]:
        return False
    return is_same_children(tree)


def is_always_false(patch):
    program = patch[list(patch.keys())[0]]
    tree, _ = program
    (cid, semantics), children = tree
    if cid not in ["not-equal", "greater-than", "less-than"]:
        return False
    return is_same_children(tree)


def is_tree_duplicate(tree, lock):
    (cid, semantics), children = tree
    if len(children) == 2:
        right_child = children['right']
        left_child = children['left']

        if cid in ["less-than", "less-or-equal", "greater-than", "greater-or-equal", "equal", "not-equal", "addition", "division", "multiplication", "subtraction"]:
            is_right_constant = is_component_constant(right_child)
            is_left_constant = is_component_constant(left_child)
            if is_right_constant and is_left_constant:
                return True
            if is_same_children(tree):
                if is_left_constant or is_right_constant:
                    return True
                else:
                    if cid in ['not-equal', 'less-than', 'greater-than']:
                        return not update_contradiction_included(lock)
                    elif cid in ['equal', 'less-or-equal', 'greater-or-equal']:
                        return not update_tautology_included(lock)
                    elif cid in ['addition', 'division', 'subtraction', 'remainder']:
                        return True
                    # else:
                    #     return True

        if cid in ["logical-or", "logical-and", "less-than", "less-or-equal", "greater-than", "greater-or-equal", "equal", "not-equal", "addition", "division", "multiplication", "subtraction"]:
            is_right_redundant = is_tree_duplicate(right_child, lock)
            is_left_redundant = is_tree_duplicate(left_child, lock)
            if is_right_redundant or is_left_redundant:
                return True
    return False


def is_tree_logic_redundant(tree):
    (cid, semantics), children = tree
    if cid in ["addition", "division", "multiplication", "subtraction", "remainder"]:
        return False
    child_node_list = extractor.extract_child_expressions(tree)
    unique_child_node_list = []
    for child in child_node_list:
        if child not in unique_child_node_list:
            unique_child_node_list.append(child)
        else:
            return True
    return False


def is_patch_duplicate(patch, index, lock):
    program = patch[list(patch.keys())[0]]
    tree, _ = program
    result = is_tree_duplicate(tree, lock) or is_tree_logic_redundant(tree)
    return result, index


def is_satisfiable(z3_code):
    parser = SmtLibParser()
    result = False
    try:
        script = parser.get_script(cStringIO(z3_code))
        formula = script.get_last_formula()
        result = is_sat(formula, solver_name="z3")
    except Exception as ex:
        emitter.debug("\t\t[warning] Z3 Exception in PYSM, Trying Z3 CLI")
        logger.information(z3_code)
        with open("/tmp/z3_cli_code", "w") as z3_file:
            z3_file.writelines(z3_code)
            z3_file.close()
        z3_cli_command = "z3 /tmp/z3_cli_code > /tmp/z3_cli_output"
        utilities.execute_command(z3_cli_command)
        with open("/tmp/z3_cli_output", "r") as log_file:
            output_content = log_file.readlines()
            if "sat" == output_content[-1].strip():
                result = True
    return result


def is_expression_equal(str_a, str_b):
    token_list = [x for x in str(str_a + str_b).split(" ")]
    prohibited_tok_list = ["(", "&"]
    if any(t in prohibited_tok_list for t in token_list):
        return False
    try:
        expr_a = sympify(str_a.replace("[", "(").replace("]", ")").replace(".", "_").replace("->", "_"))
        expr_b = sympify(str_b.replace("[", "(").replace("]", ")").replace(".", "_").replace("->", "_"))
    except Exception as ex:
        return False
    return expr_a == expr_b
