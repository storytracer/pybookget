"""Main entry point for running pybookget as a module.

Usage:
    python -m pybookget download <url>
    python -m pybookget --help
"""

from pybookget.cli import main

if __name__ == '__main__':
    main()
