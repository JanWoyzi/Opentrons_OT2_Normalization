"""Robot-side client that downloads the normalization results from the PC.

Upload this file to the OT-2 next to 1x_Norm_Protocol.py
(Jupyter folder /var/lib/jupyter/notebooks/). The secret token is NOT stored
here; it lives in a separate client settings file on the robot, which is never
committed to Git (default: /var/lib/jupyter/notebooks/normatrons_client.json):

    {
      "url": "https://169.254.52.10:5000/results",
      "token": "<token printed by results_server.py --init>",
      "ca_cert": "/var/lib/jupyter/notebooks/normatrons_cert.pem",
      "timeout_seconds": 10
    }

Written for the Python version on the OT-2 (no newer syntax features).
"""

import json  # Reads the client settings file.
import os  # Checks whether files exist.

CLIENT_CONFIG_PATH = "/var/lib/jupyter/notebooks/normatrons_client.json"  # Default location of the robot's settings.
DEFAULT_TIMEOUT_SECONDS = 10  # Give up after 10 s instead of hanging forever.


class ResultsFetchError(RuntimeError):  # Our own error type, so the protocol can catch exactly this.
    """Raised when the results cannot be retrieved safely."""  # Docstring: explains the purpose.


def load_client_config(path=CLIENT_CONFIG_PATH):  # Read the robot's settings file.
    """Return the validated client settings or raise ResultsFetchError."""  # Docstring.
    if not os.path.isfile(path):  # The settings file must exist on the robot.
        raise ResultsFetchError("Client settings file not found on the robot.")  # Stop with a clear message.
    try:  # The file might be broken JSON.
        with open(path, "r", encoding="utf-8") as handle:  # Open the settings as UTF-8 text.
            config = json.load(handle)  # Parse the JSON text into a dictionary.
    except (OSError, ValueError):  # Unreadable file or invalid JSON.
        raise ResultsFetchError("Client settings file could not be read.")  # Generic message without the token.

    url = str(config.get("url", ""))  # Full URL of the fixed results endpoint.
    if not url.endswith("/results"):  # Make sure nobody still points at the old /read_file/... endpoint.
        raise ResultsFetchError("Client 'url' must point to the /results endpoint.")  # Explain the problem.
    if not config.get("token"):  # The secret is required for every request.
        raise ResultsFetchError("Client 'token' is missing.")  # Explain the problem (without printing any token).
    if url.startswith("https://"):  # HTTPS: we must know which certificate to trust.
        ca_cert = config.get("ca_cert")  # Path of the PC's certificate copied onto the robot.
        if not ca_cert or not os.path.isfile(ca_cert):  # Without it we could not verify the PC.
            raise ResultsFetchError("Client 'ca_cert' is missing; HTTPS cannot be verified.")  # Explain.
    elif url.startswith("http://"):  # Plain HTTP: only allowed when switched on explicitly.
        if not config.get("allow_plain_http", False):  # Not switched on.
            raise ResultsFetchError("Plain HTTP is disabled; set 'allow_plain_http' or use HTTPS.")  # Explain.
    else:  # Any other scheme (ftp://, file://, ...) is not supported.
        raise ResultsFetchError("Client 'url' must start with https:// or http://.")  # Explain.
    return config  # Hand the validated settings back.


def fetch_results(config, http=None):  # Download the results text from the PC.
    """Return the results file text (the server's "content" field).

    Raises ResultsFetchError on ANY problem, so the caller can abort the run
    before a single drop is pipetted. Error messages never contain the token.
    """  # Docstring.
    if http is None:  # No HTTP library passed in (normal robot use).
        try:  # requests is installed on the OT-2, but check anyway.
            import requests as http  # Import requests under the name "http".
        except ImportError:  # requests is not available (e.g. some simulators).
            raise ResultsFetchError("The 'requests' package is not available.")  # Clear message.

    url = config["url"]  # Address of the fixed endpoint.
    headers = {"Authorization": "Bearer " + config["token"]}  # Send the secret in the Authorization header.
    verify = config.get("ca_cert") if url.startswith("https://") else True  # Trust only our own certificate for HTTPS.
    timeout = float(config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))  # Maximum waiting time in seconds.
    try:  # Network problems raise exceptions inside requests.
        response = http.get(url, headers=headers, verify=verify, timeout=timeout, allow_redirects=False)  # Send the request.
    except Exception as error:  # Timeout, connection refused, certificate check failed, ...
        raise ResultsFetchError("Could not reach the results server ({}).".format(type(error).__name__))  # Only the error type.

    if response.status_code == 401:  # Server rejected the token.
        raise ResultsFetchError("The results server rejected the token (HTTP 401).")  # Clear, secret-free message.
    if response.status_code != 200:  # Any other non-success status.
        raise ResultsFetchError("The results server returned HTTP {}.".format(response.status_code))  # Only the status code.
    try:  # The body should be JSON like {"content": "..."}.
        content = response.json()["content"]  # Pull out the file text.
    except (ValueError, KeyError, TypeError):  # Not JSON, or no "content" field.
        raise ResultsFetchError("The results server sent an unexpected response.")  # Generic message.
    if not isinstance(content, str):  # The server always sends the file as text.
        raise ResultsFetchError("The results server sent an unexpected response.")  # Generic message.
    return content  # Return the raw JSON text; decoding it into plate lists is handled in issue #2.
