from collections import namedtuple, defaultdict
import math


Location = namedtuple("Location", ["class_name", "line_number"])


class TestCount:
    def __init__(self, ex_pass=0, ex_fail=0, not_ex_pass=0, not_ex_fail=0) -> None:
        self.ex_pass = ex_pass
        self.ex_fail = ex_fail
        self.not_ex_pass = not_ex_pass
        self.not_ex_fail = not_ex_fail


class FLAlgorithm:
    def __init__(self) -> None:
        pass

    @staticmethod
    def ochiai(count):
        return (count.ex_fail /
                math.sqrt((count.ex_fail + count.not_ex_fail) * (count.ex_fail + count.ex_pass)))


class Spectra:
    def __init__(self) -> None:
        self.test_results = {}
        self.tests_for_location = defaultdict(set)
        self.locations_for_test = defaultdict(set)

    def update(self, spectra_file):
        with open(spectra_file) as f:
            for line in f:
                tmp = line.strip().split(",")
                test, result = tmp[0], tmp[1]
                assert result in ("PASS", "FAIL")
                locations = []
                for x in tmp[2:]:
                    class_name, line_number = x.split(":")
                    line_number = int(line_number)
                    locations.append(Location(class_name, line_number))

                if test in self.test_results:
                    assert self.test_results[test] == result, test
                self.test_results[test] = result

                for location in locations:
                    self.tests_for_location[location].add(test)

                self.locations_for_test[test].update(locations)

    def dump_tests_str(self):
        tmp = ["name", ",", "outcome"]

        for test, result in sorted(self.test_results.items()):
            tmp.append("\n")
            tmp.append(test)
            tmp.append(",")
            tmp.append(result)

        return "".join(tmp)

    def __get_test_counts(self):
        count_for_location = defaultdict(TestCount)
        for test, result in self.test_results.items():
            covered = self.locations_for_test[test]
            for loc in self.tests_for_location.keys():
                if result == "PASS":
                    if loc in covered:
                        count_for_location[loc].ex_pass += 1
                    else:
                        count_for_location[loc].not_ex_pass += 1
                else:
                    if loc in covered:
                        count_for_location[loc].ex_fail += 1
                    else:
                        count_for_location[loc].not_ex_fail += 1
        return count_for_location

    def __get_susp_values(self, algorithm=FLAlgorithm.ochiai):
        return {loc: algorithm(count)
                for loc, count in self.__get_test_counts().items()}

    def dump_susp_values_str(self):
        tmp = ["<className{#lineNumber,suspValue"]
        susp_values = self.__get_susp_values()
        for loc, value in sorted(susp_values.items()):
            tmp.append("\n")
            tmp.append(f"<{loc.class_name}{{#{loc.line_number},{value}")
        return "".join(tmp)
