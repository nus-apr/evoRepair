package evorepair;

import com.google.gson.Gson;
import org.junit.runner.Description;
import org.junit.runner.JUnitCore;
import org.junit.runner.notification.RunListener;
import org.junit.runner.Request;
import org.junit.runner.manipulation.Filter;

import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;

import java.util.Map;
import java.util.HashMap;
import java.util.Set;
import java.util.HashSet;

public final class PlainValidator {
    public static void main(String[] args) {
        Socket socket = null;
        try {
            socket = new Socket("localhost", Integer.parseInt(args[0]));
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(-1);
        }

        JUnitCore core = new JUnitCore();
        RecordListener listener = new RecordListener();
        core.addListener(listener);

        Map<String, Set<String>> clazz2tests = new HashMap<>();
        Set<Class> classes = new HashSet<>();

        List<String> testNames = null;

        if (args[1].equals("-f")) {
            String testNamesFile = args[2];
            try {
                testNames = Files.readAllLines(Paths.get(testNamesFile));
            } catch (IOException e) {
                e.printStackTrace();
                System.exit(-1);
            }
        } else {
            testNames = Arrays.asList(Arrays.copyOfRange(args, 1, args.length));
        }

        for (String testName: testNames) {
            try {
                String[] clazzAndMethod = testName.split("#");
                String clazz = clazzAndMethod[0];
                String method = clazzAndMethod[1];

                classes.add(Class.forName(clazzAndMethod[0]));

                if (!clazz2tests.containsKey(clazz)) {
                    clazz2tests.put(clazz, new HashSet<>(Arrays.asList(method)));
                } else {
                    clazz2tests.get(clazz).add(method);
                }
            } catch (ClassNotFoundException e) {
                e.printStackTrace();
                System.exit(-1);
            }
        }

        Filter filter = new NameFilter(clazz2tests);
        Request request = Request.classes(classes.toArray(new Class<?>[0])).filterWith(filter);
        core.run(request);

		// send listener values back from socket

        try (OutputStream os = socket.getOutputStream()) {
            PrintStream ps = new PrintStream(os);
            ps.println(new Gson().toJson(listener));
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(-1);
        }
    }
}

class RecordListener extends RunListener {
    private List<String> passingTests = new ArrayList<>();
    private List<String> failingTests = new ArrayList<>();

    // declare as transient to be ignored by Gson
    private transient String currentTest;  

    public void testStarted(Description description) {
        this.currentTest = description.getClassName() + "#" + description.getMethodName();       
        passingTests.add(this.currentTest);
    }

    public void testFailure(Description description) {
        String tmp = passingTests.remove(passingTests.size() - 1);
        assert tmp.equals(this.currentTest);
        failingTests.add(this.currentTest);
    }

    List<String> getPassingTests() {
        return new ArrayList<>(this.passingTests);
    }

    List<String> getFailingTests() {
        return new ArrayList<>(this.failingTests);
    }
}

class NameFilter extends Filter {
    private Map<String, Set<String>> clazz2tests;
    
    public NameFilter(Map<String, Set<String>> clazz2tests) {
        this.clazz2tests = clazz2tests; 
    }

    @Override
    public String describe() {
        return "Only execute test methods passed as arguments";
    }

    @Override
    public boolean shouldRun(Description description) {
        String methodName = description.getMethodName();
        if (methodName == null) {
            return true;
        }

        String testClass = description.getClassName();

        return clazz2tests.get(testClass).contains(methodName);
    }
}
