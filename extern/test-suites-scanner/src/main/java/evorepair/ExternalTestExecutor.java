package evorepair;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class ExternalTestExecutor {
    String binJavaDir;
    String binTestDir;
    String[] dependences;

    String testClassNamesPath;

    String scannerBinDir;

    boolean isIOExceptional;
    boolean isTimeout;

    public ExternalTestExecutor(String testClassNamesPath, String binJavaDir, String binTestDir, String[] dependences,
                                String scannerBinDir) {
        this.testClassNamesPath = testClassNamesPath;
        this.binJavaDir = binJavaDir;
        this.binTestDir = binTestDir;
        this.dependences = dependences;
        this.scannerBinDir = scannerBinDir;
        this.isTimeout = false;
        this.isIOExceptional = false;
    }

    public List<List<String>> runTests() throws IOException, InterruptedException {
        // TODO Auto-generated method stub
        List<String> params = new ArrayList<>();
        String jvmPath = System.getProperties().getProperty("java.home") + File.separator + "bin" + File.separator + "java";
        params.add(jvmPath);
        params.add("-cp");

        String cpStr = "";
        cpStr += (binJavaDir + File.pathSeparator);
        cpStr += (binTestDir + File.pathSeparator);
        cpStr += scannerBinDir + File.pathSeparator;
        if (dependences != null) {
            for (String dp : dependences)
                cpStr += (File.pathSeparator + dp);
        }
        params.add(cpStr);

        params.add("evorepair.JUnitTestRunner");

        params.add("@" + testClassNamesPath);

        System.out.println(String.join(" ", params));

        ProcessBuilder builder = new ProcessBuilder(params);
        builder.redirectOutput();
        builder.redirectErrorStream(true);
        builder.directory();
        builder.environment().put("TZ", "America/Los_Angeles");

        Process process = builder.start();

        StreamReaderThread streamReaderThread = new StreamReaderThread(process.getInputStream());
        streamReaderThread.start();

        int exitCode = process.waitFor();

        streamReaderThread.join();

        if (exitCode != 0 || streamReaderThread.isIOExceptional()) {
            throw new RuntimeException();
        }

        List<String> passingTests = new ArrayList<>();
        List<String> failingTests = new ArrayList<>();
        List<String> output = streamReaderThread.getOutput();
        for (String str : output) {
            if (str.startsWith("FailedTest")) {
                failingTests.add(str.split(":")[1].trim());
            }
            if (str.startsWith("PassedTest")) {
                passingTests.add(str.split(":")[1].trim());
            }
        }

        List<List<String>> result = new ArrayList<>();
        result.add(passingTests);
        result.add(failingTests);
        return result;
    }
}
