import pytest
import sys

if __name__ == '__main__':
    tests = sys.argv[1:]
    if not tests:
        tests = ['tests/test_core.py']
    sys.exit(pytest.main(tests))
