class Patch():
    def __init__(self, diff_file, strip: int, changed_classes, key):
        self.diff_file = diff_file
        self.strip = strip
        self.changed_classes = changed_classes
        self.key = key

    def __repr__(self):
        return f"Patch@{self.key}[diff={self.diff_file}, strip={self.strip}, classes={self.changed_classes}]"
