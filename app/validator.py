from app import emitter, utilities, values
from app.tester import read_evosuite_version

import shlex
import os
from pathlib import Path
import time
import subprocess
from subprocess import PIPE, DEVNULL
import xml.dom.minidom
import itertools
import re
from datetime import datetime, timezone, timedelta
import socket
import json
import glob
import asyncio
import shutil


"""
This is the function to implement the interfacing with UniAPR (optimized validation)

Expected Input
@arg list of patches
@arg list of test cases
@arg work_dir: a directory to which this function can write (but not overwrite) things

Expected Output
@output matrix of result for each test x patch
@output sorted list of plausible patches
@output ranked list of test-cases and their mutation score
"""


def validate(patches, tests, work_dir, compile_patches=True, compile_tests=True, execute_tests=True):
    assert os.path.exists(work_dir)

    emitter.sub_sub_title("Validating Generated Patches")
    emitter.normal("\trunning UniAPR")

    patch_bin_dir = Path(work_dir, "patches_bin")
    if compile_patches:
        for p in patches:
            p.compile(Path(patch_bin_dir, p.key))

    test_bin_dir = Path(work_dir, "target", "test-classes")  # UniAPR accepts maven directory structure
    if compile_tests:
        for t in tests:
            t.compile(test_bin_dir)

    if values.use_hotswap:
        changed_classes = list(itertools.chain(*(p.changed_classes for p in patches)))
        return run_uniapr(work_dir, patch_bin_dir, changed_classes, execute_tests)
    else:
        return plain_validate(patch_bin_dir, test_bin_dir, execute_tests)


def run_uniapr(work_dir, patch_bin_dir, changed_classes, execute_tests):
    # link the original class files to mock a maven directory layout
    mock_bin_dir = Path(work_dir, "target", "classes")
    os.makedirs(mock_bin_dir.parent, exist_ok=True)  # may already exist because of test compilation

    class_dir = os.path.abspath(values.dir_info["classes"])
    link_path = os.path.abspath(mock_bin_dir)
    if os.path.exists(link_path):
        target = os.path.join(os.path.dirname(link_path), os.readlink(link_path))
        assert target == class_dir
    else:
        os.symlink(class_dir, link_path)

    # set up a local maven repo
    # see https://stackoverflow.com/questions/364114/can-i-add-jars-to-maven-2-build-classpath-without-installing-them
    deps_repo_dir = Path(work_dir, "validation-maven-repo")
    os.makedirs(deps_repo_dir, exist_ok=True)
    dependency = []
    for entry in os.scandir(values.dir_info["deps"]):
        assert entry.name.endswith(".jar")
        dependency.append(symlink_jar_to_repo(entry.path, deps_repo_dir))
    evosuite_runtime_jar = Path(values._dir_root, "extern", "evosuite", "standalone_runtime",
                                "target", f"evosuite-standalone-runtime-{read_evosuite_version()}.jar")
    dependency.append(symlink_jar_to_repo(evosuite_runtime_jar, deps_repo_dir))
    junit_jar = Path(values._dir_root, "extern", "arja", "external", "lib", "junit-4.11.jar")
    dependency.append(symlink_jar_to_repo(junit_jar, deps_repo_dir))

    pom = make_uniapr_pom(dependency, deps_repo_dir.as_uri())
    with open(Path(work_dir, "pom.xml"), 'w') as f:
        f.write(pom)

    prefix = common_package_prefix(changed_classes)
    assert prefix

    uniapr_command = (f"mvn org.uniapr:uniapr-plugin:validate -DresetJVM=true"
                      f" -DpatchesPool={patch_bin_dir} -DwhiteListPrefix={prefix}"
                      )

    if execute_tests:
        emitter.command(uniapr_command)

        process = subprocess.run(shlex.split(uniapr_command), stdout=PIPE, stderr=PIPE, env=os.environ, cwd=work_dir)
        if process.returncode != 0:
            emitter.warning(f"UniAPR did not exit normally")
        with open(Path(values.dir_log_base, "uniapr.out"), 'w') as f:
            f.write(process.stdout.decode("utf8"))
        return parse_uniapr_output(process.stdout.decode("utf-8"))
    else:
        return []


def symlink_jar_to_repo(jar, repo):
    """
    Install a jar file to a local maven repo. Jar is not copied but symlinked into the repo.

    :param jar: path of jar file
    :param repo: path of repo
    :return: a 3-tuple of str: (groupId, artifactId, version)
    """
    assert os.path.exists(jar)
    assert os.path.exists(repo)
    jar = os.path.abspath(jar)
    repo = os.path.abspath(repo)

    group_id = "foo"
    artifact_id = Path(jar).stem
    version = "foo"

    path = Path(repo, *group_id.split("."), artifact_id, version, f"{artifact_id}-{version}.jar")
    os.makedirs(path.parent, exist_ok=True)
    if not path.exists():
        os.symlink(jar, path)
    else:
        target = os.path.join(os.path.dirname(path), os.readlink(path))
        assert target == jar

    return (group_id, artifact_id, version)


def make_uniapr_pom(dependency: list, repo_uri):
    deps_str = "".join([make_deps_str(*x) for x in dependency])
    s = f"""\
        <project>
            <modelVersion>4.0.0</modelVersion>
            <groupId>foo</groupId>
            <artifactId>bar</artifactId>
            <version>baz</version>
            <dependencies>{deps_str}</dependencies>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.uniapr</groupId>
                        <artifactId>uniapr-plugin</artifactId>
                        <version>1.0-SNAPSHOT</version>
                    </plugin>
                </plugins>
            </build>
            <repositories>
                <repository>
                    <id>repo</id>
                    <releases>
                        <enabled>true</enabled>
                        <checksumPolicy>ignore</checksumPolicy>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                    <url>{repo_uri}</url>
                </repository>
            </repositories>
        </project>
        """
    return prettify_xml_str(s)


def prettify_xml_str(s):
    # still ugly, but I don't want to use lxml (external library) or xmllint
    return xml.dom.minidom.parseString(s).toprettyxml(indent="  ", newl="")


def make_deps_str(group_id, artifact_id, version):
    return f"""
        <dependency>
            <groupId>{group_id}</groupId>
            <artifactId>{artifact_id}</artifactId>
            <version>{version}</version>
        </dependency>
    """


def common_package_prefix(classnames):
    assert len(classnames)
    splits = [cls.split(".") for cls in classnames]
    return ".".join(os.path.commonprefix(splits))


def parse_uniapr_output(s):
    """Parse output of UniAPR

    :param str s: standard output of UniAPR run
    :return: list of tuples of form ("patch_id", ["pass_method1", ...], ["fail_method1", ...])
    """
    patch_id = None
    test = None
    passing_tests = []
    failing_tests = []
    started = False
    result = []
    for line in s.splitlines():
        if line == "Profiler is DONE!":
            started = True
            continue
        if not started:
            continue

        if patch_id is None:
            match = re.fullmatch(r">>Validating patchID: (.*)", line)
            if match:
                patch_id = match.group(1)
                continue

        test_match = re.fullmatch(r"RUNNING:.(\S+)\.\.\.\s*", line)
        if test_match:
            assert patch_id is not None, line
            if test is not None:
                passing_tests.append(test)
            test = test_match.group(1)
            continue

        # do not use fullmatch() for this, because the warning may be entangled in stacktrace
        if re.search(r"WARNING: Running test cases is terminated", line):
            assert test is not None, line
            assert patch_id is not None, line
            failing_tests.append(test)
            result.append((patch_id, passing_tests, failing_tests))
            patch_id, test = None, None
            passing_tests, failing_tests = [], []
    return result


def plain_validate(patches_bin_dir, tests_bin_dir, execute_tests):
    if not execute_tests:
        return []

    test_class_files = glob.glob(os.path.join(tests_bin_dir, "**", "*_ESTest.class"), recursive=True)
    test_classes = []
    for file in test_class_files:
        path = Path(file).relative_to(tests_bin_dir).with_suffix("")
        test_classes.append(".".join(path.parts))

    result = []
    for entry in os.scandir(patches_bin_dir):
        key = entry.name
        message = asyncio.run(run_plain_validator(entry.path, tests_bin_dir, test_classes))
        obj = json.loads(message)
        result.append((key, obj["passingTests"], obj["failingTests"]))
    return result


async def run_plain_validator(patch_dir, test_bin_dir, test_classes):
    result = []

    async def plain_validator_connected(reader, _):
        result.append((await reader.read()).decode("utf-8"))

    server_socket = socket.socket()
    server_socket.bind(("localhost", 0))
    _, port = server_socket.getsockname()
    server = await asyncio.start_server(plain_validator_connected, sock=server_socket)
    async with server:
        await server.start_serving()
        evosuite_runtime_jar = Path(values._dir_root, "extern", "evosuite", "standalone_runtime",
                                    "target", f"evosuite-standalone-runtime-{read_evosuite_version()}.jar")
        junit_jar = Path(values._dir_root, "extern", "arja", "external", "lib", "junit-4.11.jar")
        plain_validator_jar = Path(values._dir_root, "extern", "plain-validator", "target",
                                   "plain-validator-1.0-SNAPSHOT-jar-with-dependencies.jar")

        # must put patch_dir before values.dir_info["classes"]
        classpath = [patch_dir, values.dir_info["classes"], evosuite_runtime_jar,
                     junit_jar, plain_validator_jar, test_bin_dir]
        for entry in os.scandir(values.dir_info["deps"]):
            assert entry.name.endswith(".jar")
            classpath.append(entry.path)
        classpath = [os.path.abspath(p) for p in classpath]
        command = (f'{shutil.which("java")} -cp "{":".join(classpath)}" evorepair.PlainValidator {port}'
                   f' {" ".join(test_classes)}')

        emitter.command(command)

        process = await asyncio.create_subprocess_shell(command, stdout=DEVNULL, stderr=DEVNULL)
        await process.wait()
    return result[0]
