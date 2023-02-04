package evorepair;
import java.io.File;
import java.util.Arrays;
import java.util.List;


import org.junit.runner.JUnitCore;

public class JUnitTestRunner {
    public static void main(String args[]) throws Exception {
        List<String> classes;
        if (args[0].startsWith("@")) {
            String path = args[0].trim().substring(1);
            classes = Util.readLines(new File(path));
        } else {
            String testStrs[] = args[0].trim().split(File.pathSeparator);
            classes = Arrays.asList(testStrs);
        }

        runTests(classes);
        System.exit(0);
    }

    private static void runTests(List<String> classes) throws ClassNotFoundException {
        RecordListener listener = new RecordListener();
        for (String className : classes) {
            JUnitCore core = new JUnitCore();
            core.addListener(listener);
            core.run(Class.forName(className));
        }

        printResults(listener.getPassingTests(), listener.getFailingTests());
    }

    private static void printResults(List<String> passedTests, List<String> failedTests) {
        System.out.println("FailureCount: " + failedTests.size());
        for (String test : passedTests)
            System.out.println("PassedTest: " + test);
        for (String test : failedTests)
            System.out.println("FailedTest: " + test);
    }
}
