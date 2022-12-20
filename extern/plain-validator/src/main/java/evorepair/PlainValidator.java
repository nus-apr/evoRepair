package evorepair;

import com.google.gson.Gson;
import org.junit.runner.Description;
import org.junit.runner.JUnitCore;
import org.junit.runner.notification.RunListener;

import java.net.Socket;
import java.util.ArrayList;
import java.util.List;
import java.io.OutputStream;
import java.io.PrintStream;

public final class PlainValidator {
    public static void main(String[] args) {
        Socket socket = null;
        try {
            socket = new Socket("localhost", Integer.parseInt(args[0]));
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(-1);
        }

        int numberOfTestClasses = args.length - 1;
        Class<?>[] classes = new Class<?>[numberOfTestClasses];
        for (int i = 0; i < numberOfTestClasses; i++) {
            try {
                classes[i] = Class.forName(args[i + 1]);
            } catch (ClassNotFoundException e) {
                e.printStackTrace();
                System.exit(-1);
            }
        }

        JUnitCore core = new JUnitCore();
        RecordListener listener = new RecordListener();
        core.addListener(listener);
        core.run(classes);
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
