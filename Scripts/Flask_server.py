"""Standalone launcher for the restricted Normatrons results server.

The old version of this file exposed /read_file/<any path> without a password.
It now only starts the shared, authenticated server from results_server.py,
so the standalone and GUI launch paths behave identically.

Usage (from the Scripts folder):
    python Flask_server.py                      # start the server
    python Flask_server.py --init --results-file <json> --host <pc-ip>
    python Flask_server.py --make-cert --host <pc-ip>
"""

import sys  # Gives access to sys.exit() so the exit code reaches the operating system.

from results_server import main  # Re-use the single shared server implementation.

if __name__ == "__main__":  # Only run when this file is started directly.
    sys.exit(main())  # Start the restricted server (or --init / --make-cert) and exit with its status code.
