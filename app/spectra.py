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
        ex_total = count.ex_fail + count.ex_pass
        if ex_total == 0:
            return 0
        else:
            return (count.ex_fail /
                    math.sqrt((count.ex_fail + count.not_ex_fail) * ex_total))


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
    
    def restrict(self, tests):
        result = Spectra()
        result.test_results = { test: self.test_results[test] for test in tests }
        result.tests_for_location = { loc: (self.tests_for_location[loc] & tests) for loc in self.tests_for_location }
        result.locations_for_test = { test: self.locations_for_test[test] for test in tests }
        return result

    def dump_tests_str(self):
        tmp = ["name", ",", "outcome"]

        for test, result in sorted(self.test_results.items()):
            tmp.append("\n")
            tmp.append(test)
            tmp.append(",")
            tmp.append(result)
            tmp.extend([f",{loc.class_name}:{loc.line_number}"
                        for loc in self.locations_for_test[test]])

        return "".join(tmp)

    def __get_test_counts(self, ignored_tests=None):
        count_for_location = defaultdict(TestCount)
        for test, result in self.test_results.items():
            if ignored_tests is not None and test in ignored_tests:
                continue
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

    def __get_susp_values(self, algorithm=FLAlgorithm.ochiai, ignored_tests=None):
        return {loc: algorithm(count)
                for loc, count in self.__get_test_counts(ignored_tests=ignored_tests).items()}

    def dump_susp_values_str(self, ignored_tests=None, perfect_locations=None):
        tmp = ["<className{#lineNumber,suspValue"]

        if perfect_locations is None:
            susp_values = self.__get_susp_values(ignored_tests=ignored_tests)
        else:
            # If we set the susp value of given locations to 1, and omit any other location,
            # then Arja-e is likely to crash.
            # Instead, use a high susp value for given locations, and give a susp value of 1
            # to other locations. This way, other locations don't get ruled out by Arja-e,
            # but have a very low probability of being selected.

            susp_values = {loc: 10000000 for loc in perfect_locations}
            for loc in self.__get_susp_values(ignored_tests=ignored_tests):
                if loc not in susp_values:
                    susp_values[loc] = 1

        for loc, value in sorted(susp_values.items(), reverse=True):
            tmp.append("\n")
            tmp.append(f"<{loc.class_name}{{#{loc.line_number},{value}")
        return "".join(tmp)
