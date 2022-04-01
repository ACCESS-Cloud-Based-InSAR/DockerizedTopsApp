import sys


class SysArgvManager:
    """Context manager to clear and reset sys.argv

    A bug in the ISCE2 Application class causes sys.argv to always be parsed when
    no options are proved, even when setting `cmdline=[]`, preventing programmatic use.
    """
    def __init__(self):
        self.argv = sys.argv.copy()

    def __enter__(self):
        sys.argv = sys.argv[:1]

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.argv = self.argv
