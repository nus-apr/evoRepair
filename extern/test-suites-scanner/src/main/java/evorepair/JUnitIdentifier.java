package evorepair;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

import org.junit.Test;
import junit.framework.TestCase;

public class JUnitIdentifier {
    public static List<String> getJUnitMethodNames(Class<?> target) {
        if (isAbstractClass(target)) {
            return new ArrayList<>();
        }

        Method[] methods = target.getMethods();

        if (isJUnit3TestClass(target)) {
            return Arrays.stream(methods)
                   .filter(JUnitIdentifier::isJUnit3TestMethod)
                   .map(Method::getName)
                   .collect(Collectors.toList());
        }

        return Arrays.stream(methods)
               .filter(JUnitIdentifier::isJUnit4TestMethod)
               .map(Method::getName)
               .collect(Collectors.toList());
    }

    private static boolean isAbstractClass(Class<?> target) {
        int modifiers = target.getModifiers();
        return Modifier.isAbstract(modifiers) || Modifier.isInterface(modifiers);
    }

    private static boolean isJUnit3TestClass(Class<?> target) {
        return TestCase.class.isAssignableFrom(target);
    }

    private static boolean isJUnit3TestMethod(Method method) {
        return method.getName().startsWith("test");
    }

    private static boolean isJUnit4TestMethod(Method method) {
        return method.isAnnotationPresent(Test.class);
    }
}
