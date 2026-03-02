import pytest
import sys

if __name__ == '__main__':
    # run all tests if no args
    args = sys.argv[1:]
    if not args:
        args = ['tests/test_core.py']
    res = pytest.main(args)
    sys.exit(res)
