package evorepair;

import com.google.gson.Gson;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;

import java.util.Map;
import java.util.HashMap;

import java.io.File;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class TestSuitesScanner {
    public static void main(String[] args) throws Exception {
        String port = args[0];
        String binDir = args[1];
        String testsBinDir = args[2];
        String dependences = args[3].trim();

        Socket socket = null;
        try {
            socket = new Socket("localhost", Integer.parseInt(port));
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(-1);
        }

        Map<String, List<String>> testsInClass =
            findTests(binDir, testsBinDir, dependences.isEmpty() ? new String[0] : dependences.split(":"));

        try (OutputStream os = socket.getOutputStream()) {
            PrintStream ps = new PrintStream(os);
            ps.println(new Gson().toJson(testsInClass));
            System.exit(0);
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(-1);
        }
    }

    private static Map<String, List<String>> findTests(String binDir, String testsBinDir, String[] dependences)
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

        Map<String, List<String>> result = new HashMap<>();

        int suffixLength = ".class".length();

        for (File file: classFiles) {
            String relative = testsBinURI.relativize(file.toURI()).getPath();
            String temp = relative.replace("/", ".");

            String className = temp.substring(0, temp.length() - suffixLength);

            Class<?> target = loader.loadClass(className);
            List<String> junitMethodNames = JUnitIdentifier.getJUnitMethodNames(target);
            if (!junitMethodNames.isEmpty()) {
                result.put(className, junitMethodNames);
            }
        }

        return result;
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
