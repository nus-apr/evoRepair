from app import emitter, utilities, values
from app.tester import read_evosuite_version

import shlex
import os
from pathlib import Path
import subprocess
from subprocess import PIPE
import xml.dom.minidom
import re


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
    junit_jar = Path(values.file_junit_jar)
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
        emitter.normal("\trunning UniAPR")

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
