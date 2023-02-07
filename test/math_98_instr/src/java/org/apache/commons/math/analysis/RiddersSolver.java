/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License.  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.commons.math.analysis;

import org.apache.commons.math.FunctionEvaluationException;
import org.apache.commons.math.MaxIterationsExceededException;
import org.apache.commons.math.util.MathUtils;

/**
 * Implements the <a href="http://mathworld.wolfram.com/RiddersMethod.html">
 * Ridders' Method</a> for root finding of real univariate functions. For
 * reference, see C. Ridders, <i>A new algorithm for computing a single root
 * of a real continuous function </i>, IEEE Transactions on Circuits and
 * Systems, 26 (1979), 979 - 980.
 * <p>
 * The function should be continuous but not necessarily smooth.</p>
 *  
 * @version $Revision$ $Date$
 * @since 1.2
 */
public class RiddersSolver extends UnivariateRealSolverImpl {

    /** serializable version identifier */
    private static final long serialVersionUID = -4703139035737911735L;

    /**
     * Construct a solver for the given function.
     * 
     * @param f function to solve
     */
    public RiddersSolver(UnivariateRealFunction f) {
        super(f, 100, 1E-6);
    }

    /**
     * Find a root in the given interval with initial value.
     * <p>
     * Requires bracketing condition.</p>
     * 
     * @param min the lower bound for the interval
     * @param max the upper bound for the interval
     * @param initial the start value to use
     * @return the point at which the function value is zero
     * @throws MaxIterationsExceededException if the maximum iteration count is exceeded
     * @throws FunctionEvaluationException if an error occurs evaluating the
     * function
     * @throws IllegalArgumentException if any parameters are invalid
     */
    public double solve(double min, double max, double initial) throws
        MaxIterationsExceededException, FunctionEvaluationException {

        // check for zeros before verifying bracketing
        if (f.value(min) == 0.0) { return min; }
        if (f.value(max) == 0.0) { return max; }
        if (f.value(initial) == 0.0) { return initial; }

        verifyBracketing(min, max, f);
        verifySequence(min, initial, max);
        if (isBracketing(min, initial, f)) {
            return solve(min, initial);
        } else {
            return solve(initial, max);
        }
    }

    /**
     * Find a root in the given interval.
     * <p>
     * Requires bracketing condition.</p>
     * 
     * @param min the lower bound for the interval
     * @param max the upper bound for the interval
     * @return the point at which the function value is zero
     * @throws MaxIterationsExceededException if the maximum iteration count is exceeded
     * @throws FunctionEvaluationException if an error occurs evaluating the
     * function 
     * @throws IllegalArgumentException if any parameters are invalid
     */
    public double solve(double min, double max) throws MaxIterationsExceededException, 
        FunctionEvaluationException {

        // [x1, x2] is the bracketing interval in each iteration
        // x3 is the midpoint of [x1, x2]
        // x is the new root approximation and an endpoint of the new interval
        double x1, x2, x3, x, oldx, y1, y2, y3, y, delta, correction, tolerance;

        x1 = min; y1 = f.value(x1);
        x2 = max; y2 = f.value(x2);

        // check for zeros before verifying bracketing
        if (y1 == 0.0) { return min; }
        if (y2 == 0.0) { return max; }
        verifyBracketing(min, max, f);

        int i = 1;
        oldx = Double.POSITIVE_INFINITY;
        while (i <= maximalIterationCount) {
            // calculate the new root approximation
            x3 = 0.5 * (x1 + x2);
            y3 = f.value(x3);
            if (Math.abs(y3) <= functionValueAccuracy) {
                setResult(x3, i);
                return result;
            }
            delta = 1 - (y1 * y2) / (y3 * y3);  // delta > 1 due to bracketing
            correction = (MathUtils.sign(y2) * MathUtils.sign(y3)) *
                         (x3 - x1) / Math.sqrt(delta);
            x = x3 - correction;                // correction != 0
            y = f.value(x);

            // check for convergence
            tolerance = Math.max(relativeAccuracy * Math.abs(x), absoluteAccuracy);
            if (Math.abs(x - oldx) <= tolerance) {
                setResult(x, i);
                return result;
            }
            if (Math.abs(y) <= functionValueAccuracy) {
                setResult(x, i);
                return result;
            }

            // prepare the new interval for next iteration
            // Ridders' method guarantees x1 < x < x2
            if (correction > 0.0) {             // x1 < x < x3
                if (MathUtils.sign(y1) + MathUtils.sign(y) == 0.0) {
                    x2 = x; y2 = y;
                } else {
                    x1 = x; x2 = x3;
                    y1 = y; y2 = y3;
                }
            } else {                            // x3 < x < x2
                if (MathUtils.sign(y2) + MathUtils.sign(y) == 0.0) {
                    x1 = x; y1 = y;
                } else {
                    x1 = x3; x2 = x;
                    y1 = y3; y2 = y;
                }
            }
            oldx = x;
            i++;
        }
        throw new MaxIterationsExceededException(maximalIterationCount);
    }
}
