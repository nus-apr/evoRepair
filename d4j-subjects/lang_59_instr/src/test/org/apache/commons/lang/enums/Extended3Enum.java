/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package org.apache.commons.lang.enums;

import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Extended enumeration.
 *
 * @author Stephen Colebourne
 * @version $Id$
 */
public class Extended3Enum extends Extended2Enum {
    public static final Extended1Enum DELTA = new Extended3Enum("Delta");

    protected Extended3Enum(String name) {
        super(name);
    }

    public static Extended1Enum getEnum(String name) {
        return (Extended1Enum) Enumeration.getEnum(Extended3Enum.class, name);
    }

    public static Map getEnumMap() {
        return Enumeration.getEnumMap(Extended3Enum.class);
    }

    public static List getEnumList() {
        return Enumeration.getEnumList(Extended3Enum.class);
    }

    public static Iterator iterator() {
        return Enumeration.iterator(Extended3Enum.class);
    }

}
