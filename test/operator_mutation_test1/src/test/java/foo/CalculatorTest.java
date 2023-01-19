package foo;

import static org.junit.Assert.assertTrue;
import org.junit.Test;

public class CalculatorTest {
    @Test
    public void test1() {
        assertTrue(!Calculator.less(1, 1));
    }
}