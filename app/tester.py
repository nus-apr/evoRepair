from app import emitter, utilities, values
import os
import datetime


"""
This function implements the developer testing to generate test-diagnostics for the repair 

"""
def generate_test_diagnostic():
    emitter.normal("running developer test-suite")

"""
This is the interface for EvoSuite
# Expected Input
# @arg class_name: fully-qualified target class name for testing
# @arg class_path: absolute path for the target build files
# @arg output_dir: (absolute or relative) path to directory in which EvoSuite will place the tests and reports
# Expected Output
# @output list of test-cases JSON format
"""
def generate_additional_test(class_name, class_path, output_dir):
    emitter.sub_sub_title("Generating Test Cases")

    emitter.normal("\trunning evosuite")
    class_name = "org.jfree.chart.renderer.category.AbstractCategoryItemRenderer"
    class_path = f"{values._dir_root}/test/chart_1_buggy/build/"
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    output_dir = f"{values.dir_output}/evosuite_chart_1_buggy_{now.strftime('%d%b%H:%M:%S')}"
    return []

    dir_evosuite = f"{values._dir_root}/extern/evosuite"
    evosuite_version = '1.2.1-SNAPSHOT'
    evosuite_jar_path = f"{dir_evosuite}/master/target/evosuite-master-{evosuite_version}.jar"

    # Create output dir if not already existing
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Create and invoke EvoSuite command
    generate_command = (f"java -jar {evosuite_jar_path} -class {class_name} -projectCP {class_path}"
                        f" -base_dir {output_dir} -Dassertions=false"
                       )
    utilities.execute_command(generate_command)

    # Get tests generated by EvoSuite
    # TODO: EvoSuite produces two .java-files per class C: C_ESTest.java and C_ESTest_scaffolding.java.
    #       The scaffolding class contains setup code to make the tests deterministic and is inherited by the other.
    #       Technically it should be enough to only return the ESTest.java.

    # Get directory structure from class name,  e.g. 'some.package.prefix.MyClass' -> 'some/package/prefix'
    # TODO: This assumes that we only have one test class or all test classes are in the same package. Is this the case?
    package_prefix = str(os.path.sep).join(class_name.split(".")[:-1])
    generated_tests_path = os.path.join(output_dir, "evosuite-tests", package_prefix)

    list_tests = []
    for r, _, f in os.walk(generated_tests_path):
        for file in f:
            if '.java' in file:
                list_tests.append(os.path.join(r, file))

    return list_tests


