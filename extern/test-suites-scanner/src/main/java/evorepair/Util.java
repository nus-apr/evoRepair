package evorepair;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;

public class Util {
    public static List<String> readLines(File file) throws IOException {
        FileInputStream fstream = new FileInputStream(file);
        BufferedReader br = new BufferedReader(new InputStreamReader(fstream));

        String strLine;
        List<String> lines = new ArrayList<String>();
        while ((strLine = br.readLine()) != null)
            lines.add(strLine.trim());
        br.close();
        return lines;
    }
}
