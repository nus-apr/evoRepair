from app import emitter, utilities, values

import shlex
import os
from pathlib import Path
import time
import subprocess
from subprocess import PIPE
import textwrap
import xml.dom.minidom

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
def validate(patches, tests):
    emitter.sub_sub_title("Validating Generated Patches")
    emitter.normal("\trunning UniAPR")

    out_dir = Path(values.dir_tmp, f"{time.time()}")
    assert not out_dir.exists()

    patch_bin_dir = Path(out_dir, "patches_bin")
    for p in patches:
        p.compile(Path(patch_bin_dir, p.key))

    test_bin_dir = Path(out_dir, "target", "test-classes")  # UniAPR accepts maven directory structure
    for t in tests:
        t.compile(test_bin_dir)

    # set up a local maven repo
    # see https://stackoverflow.com/questions/364114/can-i-add-jars-to-maven-2-build-classpath-without-installing-them
    deps_repo_dir = Path(out_dir, "validation-maven-repo")
    os.makedirs(deps_repo_dir)
    dependency = []
    for entry in os.scandir(values.dir_info["deps"]):
        assert entry.name.endswith(".jar")
        dependency.append(symlink_jar_to_repo(entry.path, deps_repo_dir))
    evosuite_runtime_jar = Path(values._dir_root, "extern", "evosuite", "standalone_runtime",
                                "target", "evosuite-standalone-runtime-1.2.1-SNAPSHOT.jar")
    dependency.append(symlink_jar_to_repo(evosuite_runtime_jar, deps_repo_dir))
    junit_jar = Path(values._dir_root, "extern", "arja", "external", "lib", "junit-4.11.jar")
    dependency.append(symlink_jar_to_repo(junit_jar, deps_repo_dir))

    pom = make_uniapr_pom(dependency, deps_repo_dir.as_uri())
    with open(Path(out_dir, "pom.xml"), 'w') as f:
        f.write(pom)


    uniapr_command = f"mvn org.uniapr:uniapr-plugin:validate -DresetJVM=true -DpatchesPool={patch_bin_dir}"

    emitter.command(uniapr_command)

    process = subprocess.run(shlex.split(uniapr_command), stdout=PIPE, stderr=PIPE, env=os.environ, cwd=out_dir)
    if process.returncode != 0:
        utilities.error_exit(f"UniAPR EXECUTION FAILED!!\nExit Code: {process.returncode}")

    failed_patches = parse_uniapr_output(process.stdout.decode("utf-8"))

    return failed_patches


def write_uniapr_pom(out_dir):
    s = textwrap.dedent("""\
        <project>
            <modelVersion>4.0.0</modelVersion>
            <groupId>foo</groupId>
            <artifactId>bar</artifactId>
            <version>baz</version>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.uniapr</groupId>
                        <artifactId>uniapr-plugin</artifactId>
                        <version>1.0-SNAPSHOT</version>
                    </plugin>
                </plugins>
            </build>
        </project>
    """)
    with open(Path(out_dir, "pom.xml"), 'w') as f:
        f.write(s)


def symlink_jar_to_repo(jar, repo):
    """
    Install a jar file to a local maven repo. Jar is not copied but symlinked into the repo.

    :param jar: path of jar file
    :param repo: path of repo
    :return: a 3-tuple of str: (groupId, artifactId, version)
    """
    pass
    assert os.path.exists(repo)
    group_id = "foo"
    artifact_id = Path(jar).stem
    version = "foo"

    path = Path(repo, *group_id.split("."), artifact_id, version, f"{artifact_id}-{version}.jar")
    assert not path.exists()
    os.makedirs(path.parent, exist_ok=True)
    os.symlink(jar, path)

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


def parse_uniapr_output(out):
    return []