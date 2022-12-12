from app import emitter, utilities, values

class TestSuite():
    def __init__(self, dir_src, CUT, junit_classes, compile_deps: list, runtime_deps: list, key):
        self.dir_src = dir_src
        self.junit_classes = junit_classes
        self.compile_deps = compile_deps
        self.runtime_deps = runtime_deps
        assert len(junit_classes) == 1
        self.key = key
        self.CUT = CUT

    def __repr__(self):
        return f"TestSuite[src: {self.dir_src}, junits: {self.junit_classes}]"
