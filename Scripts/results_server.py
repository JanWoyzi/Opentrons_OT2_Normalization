"""Restricted, authenticated server that hands ONE results file to the OT-2.

This module is the only server implementation in the project. Both the
standalone launcher (Flask_server.py) and the GUI button in Normalization.py
use it, so there is no second, unrestricted endpoint left anywhere.

Security model (see README, section "Computer-to-robot communication"):
- one fixed endpoint, GET /results, no client-chosen file names or paths;
- the file to serve is set by the administrator in a settings file that is
  stored OUTSIDE the repository (default: ~/.normatrons/server_config.json);
- every request must send "Authorization: Bearer <token>"; the token is a
  long random secret generated with --init;
- served by the production WSGI server "cheroot" (not Flask's dev server),
  with HTTPS when a certificate is configured;
- generic error messages only, and "do not cache" headers on every response.
"""

import argparse  # Reads command-line options such as --init or --make-cert.
import hmac  # Provides compare_digest() for a timing-safe token comparison.
import json  # Reads/writes the settings file and checks that the results are valid JSON.
import os  # Reads environment variables and sets file permissions.
import secrets  # Generates cryptographically strong random tokens.
import sys  # Gives access to sys.exit() for clean error exits.
from pathlib import Path  # Object-oriented, OS-independent file paths.

from flask import Flask, jsonify, request  # Web framework, JSON responses, and the current request.

def default_settings_path():  # Where the settings live when no path is given.
    """Return the settings path: $NORMATRONS_SERVER_CONFIG or ~/.normatrons/server_config.json."""  # Docstring.
    return Path(os.environ.get(  # Look the environment variable up every time (handy for tests).
        "NORMATRONS_SERVER_CONFIG",  # Name of the optional environment variable that overrides the location.
        str(Path.home() / ".normatrons" / "server_config.json"),  # Fallback in your home folder, on Windows C:/Users/<you>/.normatrons/.
    ))  # Close the Path(...) call.


MIN_TOKEN_LENGTH = 32  # Refuse short tokens; 32+ random URL-safe characters are practically unguessable.
MAX_RESULTS_BYTES = 1_000_000  # Refuse to serve files larger than 1 MB; real results are a few kB.
BIND_ALL_INTERFACES = {"0.0.0.0", "::", ""}  # Host values that would listen on every network card.

# Headers added to every response so neither the robot nor any proxy stores the data.
NO_CACHE_HEADERS = {  # Dictionary of header name -> header value.
    "Cache-Control": "no-store, max-age=0",  # Tell every cache not to keep a copy.
    "Pragma": "no-cache",  # Same instruction for old HTTP/1.0 caches.
    "X-Content-Type-Options": "nosniff",  # Stop clients from guessing a different content type.
}  # End of the header dictionary.


class SettingsError(Exception):  # Our own error type for problems in the settings file.
    """Raised when the server settings are missing or unsafe."""  # Docstring: explains when this error is used.


def load_settings(path=None):  # Read and check the administrator's settings file.
    """Return a validated settings dictionary or raise SettingsError."""  # Docstring for the function.
    settings_path = Path(path) if path else default_settings_path()  # Use the given path or the default one.
    if not settings_path.is_file():  # The settings file must exist before the server can start.
        raise SettingsError(  # Stop with a helpful message for the administrator (not sent to the robot).
            f"Settings file not found: {settings_path}. "  # Say where we looked.
            "Create it with: python results_server.py --init --results-file <path> --host <ip>"  # Say how to fix it.
        )  # End of the error message.
    with open(settings_path, "r", encoding="utf-8") as handle:  # Open the settings file as UTF-8 text.
        settings = json.load(handle)  # Parse the JSON text into a Python dictionary.

    token = str(settings.get("token", ""))  # Read the shared secret (empty string if missing).
    if len(token) < MIN_TOKEN_LENGTH:  # Reject missing or too-short tokens.
        raise SettingsError("The token is missing or shorter than 32 characters; run --init again.")  # Explain the problem.

    results_file = settings.get("results_file")  # Read the single file the server is allowed to return.
    if not results_file:  # The administrator must name the file explicitly.
        raise SettingsError("'results_file' is not set in the settings file.")  # Explain the problem.
    settings["results_file"] = str(Path(results_file).expanduser().resolve())  # Turn it into a clean absolute path.

    host = str(settings.get("host", "")).strip()  # Read the network address to listen on.
    if host in BIND_ALL_INTERFACES:  # Listening on every interface is exactly what the issue asks us to stop.
        raise SettingsError("Set 'host' to the IP address of the network card connected to the robot, not 0.0.0.0.")  # Explain.
    settings["host"] = host  # Store the cleaned host value.
    settings["port"] = int(settings.get("port", 5000))  # Use port 5000 unless another port is configured.

    certfile = settings.get("certfile")  # Optional TLS certificate (enables HTTPS).
    keyfile = settings.get("keyfile")  # Optional TLS private key belonging to the certificate.
    if bool(certfile) != bool(keyfile):  # Exactly one of the two is set: that is a configuration mistake.
        raise SettingsError("Set both 'certfile' and 'keyfile' for HTTPS, or neither.")  # Explain.
    if not certfile and not settings.get("allow_plain_http", False):  # No HTTPS and no explicit opt-in to plain HTTP.
        raise SettingsError(  # Refuse to start so plain HTTP is always a deliberate decision.
            "No certificate configured. Either add 'certfile'/'keyfile' (recommended), or set "  # Recommended fix.
            "'allow_plain_http': true if the robot is on a direct, private cable (token is NOT encrypted)."  # Alternative.
        )  # End of the error message.
    return settings  # Hand the validated settings back to the caller.


def _error(status, message):  # Small helper to build a generic JSON error response.
    """Return a JSON error with a fixed, non-revealing message."""  # Docstring.
    return jsonify({"error": message}), status  # Flask accepts a (body, status code) tuple.


def _is_authorized(expected_token):  # Check the Authorization header of the current request.
    """True only if the request carries 'Bearer <expected_token>'."""  # Docstring.
    header = request.headers.get("Authorization", "")  # Read the header, or "" when it is missing.
    scheme, _, supplied = header.partition(" ")  # Split "Bearer abc..." into "Bearer" and "abc...".
    if scheme.lower() != "bearer" or not supplied:  # Wrong scheme or no token at all.
        return False  # Not authorized.
    return hmac.compare_digest(supplied.encode("utf-8"), expected_token.encode("utf-8"))  # Constant-time comparison.


def create_app(settings):  # Build the Flask application from validated settings.
    """Create the Flask app with exactly one authenticated endpoint."""  # Docstring.
    app = Flask(__name__)  # Create a new Flask application object.
    app.config["DEBUG"] = False  # Never run with the interactive debugger (it allows code execution).
    app.config["PROPAGATE_EXCEPTIONS"] = False  # Let our error handler answer instead of printing tracebacks to clients.
    expected_token = settings["token"]  # Keep the secret in a local variable used by the route.
    results_path = Path(settings["results_file"])  # The ONLY file this server will ever open.

    @app.route("/results", methods=["GET"])  # The single fixed endpoint; no file name in the URL.
    def results():  # Function Flask calls for GET /results.
        if not _is_authorized(expected_token):  # Check credentials BEFORE touching the file system.
            response, status = _error(401, "Unauthorized")  # Generic 401 response.
            response.headers["WWW-Authenticate"] = "Bearer"  # Standard header telling the client which scheme to use.
            return response, status  # Send the 401 back.
        try:  # Anything below may fail (file missing, locked, too big, invalid JSON).
            if results_path.stat().st_size > MAX_RESULTS_BYTES:  # Refuse unexpectedly large files.
                return _error(500, "Results unavailable")  # Generic message; no size or path revealed.
            content = results_path.read_text(encoding="utf-8")  # Read the configured results file as text.
            json.loads(content)  # Make sure it is valid JSON; raises ValueError if not.
        except FileNotFoundError:  # The GUI has not saved results yet.
            return _error(503, "Results unavailable")  # 503 = "try again later"; no path in the message.
        except (OSError, ValueError):  # Permission problems, locked file, broken JSON, wrong encoding...
            return _error(500, "Results unavailable")  # Same generic message, so nothing leaks.
        return jsonify({"content": content})  # Same response shape as before: the file text in "content".

    @app.errorhandler(404)  # Any other URL, including the old /read_file/... paths.
    def not_found(_error_obj):  # Flask passes the error object; we ignore it.
        return _error(404, "Not found")  # Generic answer, the file system is never consulted.

    @app.errorhandler(405)  # Wrong HTTP method, e.g. POST /results.
    def method_not_allowed(_error_obj):  # Flask passes the error object; we ignore it.
        return _error(405, "Method not allowed")  # Generic answer.

    @app.errorhandler(Exception)  # Safety net for any unexpected bug.
    def internal_error(_error_obj):  # Flask passes the exception; we do NOT echo it to the client.
        return _error(500, "Internal server error")  # Generic answer without exception text.

    @app.after_request  # Runs after every request, including errors.
    def add_security_headers(response):  # Receives the response that is about to be sent.
        response.headers.update(NO_CACHE_HEADERS)  # Add the "do not cache" headers.
        return response  # Hand the modified response back to Flask.

    return app  # Return the finished application.


def build_server(settings, app=None):  # Wrap the Flask app in the production cheroot server.
    """Return a cheroot WSGI server (HTTPS if a certificate is configured)."""  # Docstring.
    from cheroot.wsgi import Server as WSGIServer  # Production-grade, pure-Python server that also works on Windows.

    app = app or create_app(settings)  # Build the app unless one was passed in (useful for tests).
    server = WSGIServer((settings["host"], settings["port"]), app)  # Listen only on the configured address and port.
    if settings.get("certfile"):  # HTTPS requested?
        from cheroot.ssl.builtin import BuiltinSSLAdapter  # TLS support based on Python's ssl module.
        server.ssl_adapter = BuiltinSSLAdapter(settings["certfile"], settings["keyfile"])  # Load certificate and key.
    return server  # The caller decides when to start/stop it.


def server_url(settings):  # Human-readable address, shown to the user.
    """Return the URL the robot must use, e.g. https://169.254.52.10:5000/results."""  # Docstring.
    scheme = "https" if settings.get("certfile") else "http"  # Choose the scheme from the settings.
    return f"{scheme}://{settings['host']}:{settings['port']}/results"  # Assemble the URL.


def init_settings(path, results_file, host, port):  # Implements the --init command.
    """Write a new settings file with a fresh random token and print the token once."""  # Docstring.
    path = Path(path)  # Make sure we have a Path object.
    path.parent.mkdir(parents=True, exist_ok=True)  # Create ~/.normatrons if it does not exist yet.
    settings = {  # Content of the new settings file.
        "results_file": str(Path(results_file).expanduser().resolve()),  # Absolute path of the one file to serve.
        "token": secrets.token_urlsafe(32),  # 32 random bytes -> about 43 URL-safe characters.
        "host": host,  # IP address of the PC's network card that is connected to the robot.
        "port": port,  # TCP port, 5000 by default.
        "certfile": None,  # Filled in by --make-cert (or by hand) to enable HTTPS.
        "keyfile": None,  # Filled in by --make-cert (or by hand) to enable HTTPS.
        "allow_plain_http": False,  # Plain HTTP must be switched on deliberately.
    }  # End of the settings dictionary.
    with open(path, "w", encoding="utf-8") as handle:  # Create/overwrite the settings file.
        json.dump(settings, handle, indent=2)  # Write it as readable, indented JSON.
    try:  # chmod only has a real effect on Linux/macOS.
        os.chmod(path, 0o600)  # Owner may read/write; nobody else may read the secret.
    except OSError:  # On some file systems chmod is not supported.
        pass  # Ignore; on Windows the user profile folder is already private.
    print(f"Settings written to {path}")  # Tell the user where the file is.
    print("Copy this token into the robot's client settings (it is shown only now):")  # Explain what to do next.
    print(settings["token"])  # Show the token once, so it can be copied to the robot.


def make_certificate(settings_path, host, days=825):  # Implements the --make-cert command.
    """Create a self-signed certificate for `host` and register it in the settings."""  # Docstring.
    import datetime  # Needed for the certificate validity period.
    import ipaddress  # Turns "169.254.52.10" into an IP object for the certificate.
    from cryptography import x509  # Library that builds X.509 certificates (pip install cryptography).
    from cryptography.hazmat.primitives import hashes, serialization  # Hash algorithm and PEM file writing.
    from cryptography.hazmat.primitives.asymmetric import ec  # Elliptic-curve keys (small and fast).
    from cryptography.x509.oid import NameOID  # Standard field names such as "Common Name".

    settings_path = Path(settings_path)  # Make sure we have a Path object.
    with open(settings_path, "r", encoding="utf-8") as handle:  # Open the existing settings file.
        settings = json.load(handle)  # Load it so we can add the certificate paths.
    folder = settings_path.parent  # Store the certificate next to the settings file, outside the repo.
    key = ec.generate_private_key(ec.SECP256R1())  # Generate a new private key.
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Normatrons results server")])  # Certificate name.
    now = datetime.datetime.now(datetime.timezone.utc)  # Current time in UTC.
    cert = (  # Build the certificate step by step.
        x509.CertificateBuilder()  # Start an empty certificate.
        .subject_name(name)  # Who the certificate belongs to.
        .issuer_name(name)  # Self-signed: issuer and subject are the same.
        .public_key(key.public_key())  # Public half of our key.
        .serial_number(x509.random_serial_number())  # Unique random serial number.
        .not_valid_before(now - datetime.timedelta(minutes=5))  # Valid from 5 minutes ago (clock tolerance).
        .not_valid_after(now + datetime.timedelta(days=days))  # Valid for about two years.
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]), critical=False)  # Bind it to the PC's IP.
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)  # Lets the robot trust it directly.
        .sign(key, hashes.SHA256())  # Sign the certificate with our own key.
    )  # End of the certificate builder.
    certfile = folder / "normatrons_cert.pem"  # Public certificate: copy this one to the robot.
    keyfile = folder / "normatrons_key.pem"  # Private key: never copy or share this one.
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))  # Save the certificate as PEM text.
    keyfile.write_bytes(key.private_bytes(  # Save the private key as PEM text...
        serialization.Encoding.PEM,  # ...in PEM format,
        serialization.PrivateFormat.PKCS8,  # ...in the standard PKCS#8 layout,
        serialization.NoEncryption(),  # ...without a password (the server must read it unattended).
    ))  # End of the key writing call.
    try:  # Restrict access to the private key where the OS supports it.
        os.chmod(keyfile, 0o600)  # Owner read/write only.
    except OSError:  # Not supported on this file system.
        pass  # Ignore.
    settings.update({"certfile": str(certfile), "keyfile": str(keyfile), "host": host})  # Register HTTPS in the settings.
    with open(settings_path, "w", encoding="utf-8") as handle:  # Re-open the settings file for writing.
        json.dump(settings, handle, indent=2)  # Save the updated settings.
    print(f"Certificate: {certfile}  (copy this file to the robot)")  # Tell the user what to copy.
    print(f"Private key: {keyfile}  (keep this file on the PC only)")  # Warn the user what to keep private.


def main(argv=None):  # Entry point for "python results_server.py ...".
    """Command-line interface: run the server, or create settings/certificates."""  # Docstring.
    parser = argparse.ArgumentParser(description="Normatrons restricted results server")  # Create the option parser.
    parser.add_argument("--config", default=str(default_settings_path()), help="Path of the settings file")  # Where the settings live.
    parser.add_argument("--init", action="store_true", help="Create a settings file with a new random token")  # Setup mode.
    parser.add_argument("--results-file", help="Results JSON to serve (used with --init)")  # File for --init.
    parser.add_argument("--host", help="IP address of the PC on the robot network (used with --init/--make-cert)")  # Address.
    parser.add_argument("--port", type=int, default=5000, help="TCP port (used with --init)")  # Port number.
    parser.add_argument("--make-cert", action="store_true", help="Create a self-signed HTTPS certificate")  # Certificate mode.
    args = parser.parse_args(argv)  # Read the options from the command line.

    if args.init:  # The user wants to create a settings file.
        if not args.results_file or not args.host:  # Both values are required for a useful file.
            parser.error("--init needs --results-file and --host")  # Print usage and exit.
        init_settings(args.config, args.results_file, args.host, args.port)  # Write the settings file.
        return 0  # Exit code 0 = success.
    if args.make_cert:  # The user wants an HTTPS certificate.
        if not args.host:  # The certificate must contain the PC's IP address.
            parser.error("--make-cert needs --host")  # Print usage and exit.
        make_certificate(args.config, args.host)  # Create certificate + key and update the settings.
        return 0  # Exit code 0 = success.

    try:  # Normal mode: start the server.
        settings = load_settings(args.config)  # Read and validate the settings.
    except (SettingsError, ValueError, OSError) as error:  # Bad/missing settings or broken JSON.
        print(f"Cannot start server: {error}", file=sys.stderr)  # Explain locally; nothing is sent over the network.
        return 1  # Exit code 1 = failure.
    server = build_server(settings)  # Create the production server.
    print(f"Serving the configured results file at {server_url(settings)} (Ctrl+C to stop)")  # Show the robot URL.
    if not settings.get("certfile"):  # Plain HTTP was explicitly allowed.
        print("WARNING: plain HTTP - the token and results travel unencrypted.")  # Remind the user.
    try:  # Run until the user presses Ctrl+C.
        server.prepare()  # Open the network socket now, so a busy port fails immediately with a clear error.
        server.serve()  # Blocks here and handles requests.
    except KeyboardInterrupt:  # Ctrl+C pressed.
        pass  # Fall through to the clean shutdown.
    finally:  # Always executed, even after an error.
        server.stop()  # Close the network socket cleanly.
    return 0  # Exit code 0 = success.


if __name__ == "__main__":  # Only true when the file is started directly, not when imported.
    sys.exit(main())  # Run main() and pass its exit code to the operating system.
