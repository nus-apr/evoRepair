package evorepair;

import com.google.gson.Gson;

import java.io.*;
import java.lang.reflect.Modifier;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

import org.junit.runner.Description;
import org.junit.runner.notification.RunListener;
import org.junit.runner.notification.Failure;

import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;

public class TestSuitesRunningScanner {
    public static void main(String[] args) throws Exception {
        String port = args[0];
        String binDir = args[1];
        String testsBinDir = args[2];
        String dependences = args[3].trim();
        String scannerBinDir = args[4];
        String classNamesFile = args[5];

        Socket socket = null;
        try {
            socket = new Socket("localhost", Integer.parseInt(port));
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(-1);
        }

        String[] depArray = dependences.isEmpty() ? new String[0] : dependences.split(":");

        List<String> testClasses =
                findTestClasses(binDir, testsBinDir, depArray);

        RecordListener listener = runTestClasses(testClasses, binDir, testsBinDir, depArray, scannerBinDir, classNamesFile);

        try (OutputStream os = socket.getOutputStream()) {
            PrintStream ps = new PrintStream(os);
            ps.println(new Gson().toJson(listener));
            System.exit(0);
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(-1);
        }
    }

    public static RecordListener runTestClasses(List<String> classNames, String binDir, String testsBinDir,
                                                String[] dependences, String scannerBinDir, String classNamesFile)
            throws Exception {

        try (PrintWriter writer = new PrintWriter(classNamesFile)) {
            writer.write(String.join("\n", classNames));
        }

        ExternalTestExecutor executor = new ExternalTestExecutor(classNamesFile, binDir, testsBinDir, dependences,
                                                                 scannerBinDir);
        List<List<String>> testResult = executor.runTests();

        RecordListener listener = new RecordListener();
        listener.passingTests = testResult.get(0);
        listener.failingTests = testResult.get(1);
        return listener;
    }

    private static List<String> findTestClasses(String binDir, String testsBinDir, String[] dependences)
            throws IOException, ClassNotFoundException {
        List<File> classFiles = findClassFiles(testsBinDir);

        URI testsBinURI = new File(testsBinDir).toURI();
        URI binURI = new File(binDir).toURI();

        URL[] urls = new URL[dependences.length + 2];
        urls[0] = testsBinURI.toURL();
        urls[1] = binURI.toURL();
        for (int i = 0; i < dependences.length; i++) {
            urls[i + 2] = new File(dependences[i]).toURI().toURL();
        }

        URLClassLoader loader = new URLClassLoader(urls);

        int suffixLength = ".class".length();

        List<String> classes = new ArrayList<>();

        for (File file: classFiles) {
            String relative = testsBinURI.relativize(file.toURI()).getPath();
            String temp = relative.replace("/", ".");

            String className = temp.substring(0, temp.length() - suffixLength);

            Class<?> target = loader.loadClass(className);
            if (JUnitClassIdentifier.isJUnitTest(target) && !isAbstractClass(target)) {
                classes.add(className);
            }
        }

        return classes;
    }

    public static boolean isAbstractClass(Class<?> target) {
        int mod = target.getModifiers();
        boolean isAbstract = Modifier.isAbstract(mod);
        boolean isInterface = Modifier.isInterface(mod);

        if (isAbstract || isInterface)
            return true;

        return false;
    }

    private static List<File> findClassFiles(String directory) throws IOException {
        PathMatcher matcher = FileSystems.getDefault().getPathMatcher(String.format("glob:%s/**/*.class", directory));

        final List<File> result = new ArrayList<>();

        Files.walkFileTree(Paths.get(directory), new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                if (matcher.matches(file)) {
                    result.add(file.toFile());
                }
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFileFailed(Path file, IOException e) {
                return FileVisitResult.CONTINUE;
            }
        });

        return result;
    }
}

class RecordListener extends RunListener {
    public List<String> passingTests = new ArrayList<>();
    public List<String> failingTests = new ArrayList<>();

    // declare as transient to be ignored by Gson
    private transient String currentTest;

    public void testStarted(Description description) {
        this.currentTest = description.getClassName() + "#" + description.getMethodName();
        passingTests.add(this.currentTest);
    }

    public void testFailure(Failure failure) {
        String tmp = passingTests.remove(passingTests.size() - 1);
        assert tmp.equals(this.currentTest);
        failingTests.add(this.currentTest);
    }

    public List<String> getPassingTests() {
        return new ArrayList<>(this.passingTests);
    }

    public List<String> getFailingTests() {
        return new ArrayList<>(this.failingTests);
    }
}