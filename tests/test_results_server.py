"""Tests for issue #5: restricted, authenticated results server and robot client.

Run from the repository root with:  python -m pytest -v
"""

import ast  # Lets us pull single functions out of the robot protocol without importing opentrons.
import json  # Writes settings/results files for the tests.
import os  # Sets environment variables for the GUI (offscreen Qt, settings path).
import socket  # Finds a free TCP port for the live-server tests.
import sys  # Lets the tests import modules from the Scripts folder.
import threading  # Runs the live server in the background during a test.
from pathlib import Path  # Convenient file paths.

import pytest  # The test framework.
import requests  # Real HTTP client, the same library the robot uses.

SCRIPTS = Path(__file__).resolve().parents[1] / "Scripts"  # Folder that contains the project scripts.
sys.path.insert(0, str(SCRIPTS))  # Make "import results_server" work.

import results_client  # noqa: E402  Robot-side client under test.
import results_server  # noqa: E402  Server under test.

TOKEN = "t" * 20 + "secret-token-for-tests-1234567890"  # A long dummy token (>= 32 characters).
RESULTS = [[1.0, 2.5, 0], [3.0]]  # Small example results; the real file holds 96 values per plate.


# ---------------------------------------------------------------- helpers ---

def free_port():  # Ask the OS for an unused port so tests never collide.
    with socket.socket() as sock:  # Temporary socket.
        sock.bind(("127.0.0.1", 0))  # Port 0 = "pick any free port".
        return sock.getsockname()[1]  # Return the chosen port number.


@pytest.fixture  # pytest creates this fresh for each test that asks for it.
def setup(tmp_path):  # tmp_path is an empty temporary folder provided by pytest.
    results_file = tmp_path / "normalization_results.json"  # The one file the server may serve.
    results_file.write_text(json.dumps(RESULTS), encoding="utf-8")  # Write valid results.
    secret_file = tmp_path / "secret.txt"  # A file that must NEVER be reachable.
    secret_file.write_text("do not leak", encoding="utf-8")  # Its content.
    settings = {  # Plain-HTTP settings on the loopback interface.
        "results_file": str(results_file), "token": TOKEN, "host": "127.0.0.1",  # File, secret, interface.
        "port": free_port(), "certfile": None, "keyfile": None, "allow_plain_http": True,  # Port and HTTP opt-in.
    }  # End of settings.
    settings_path = tmp_path / "server_config.json"  # Where the settings are stored.
    settings_path.write_text(json.dumps(settings), encoding="utf-8")  # Save them.
    return {"tmp": tmp_path, "results": results_file, "secret": secret_file, "path": settings_path}  # Hand everything to the test.


@pytest.fixture  # Flask's built-in test client (no network needed).
def client(setup):  # Depends on the setup fixture above.
    settings = results_server.load_settings(setup["path"])  # Load and validate settings like the real server.
    return results_server.create_app(settings).test_client()  # Return a fake browser for the app.


AUTH = {"Authorization": "Bearer " + TOKEN}  # Correct header used in many tests.


def run_live(server):  # Start a cheroot server in a background thread.
    server.prepare()  # Open the socket.
    thread = threading.Thread(target=server.serve, daemon=True)  # Serve in the background.
    thread.start()  # Go.
    return thread  # Not used, but handy for debugging.


# ------------------------------------------------- authentication (401) ---

@pytest.mark.parametrize("headers", [  # Run the same test with several bad headers.
    {},  # No header at all.
    {"Authorization": "Bearer wrong-token"},  # Wrong token.
    {"Authorization": "Basic " + TOKEN},  # Right token, wrong scheme.
    {"Authorization": "Bearer"},  # Scheme without token.
])  # End of the parameter list.
def test_missing_or_wrong_credentials_return_401(client, headers):  # Acceptance: 401 without credentials.
    response = client.get("/results", headers=headers)  # Send the request.
    assert response.status_code == 401  # Must be rejected.
    assert response.headers["WWW-Authenticate"] == "Bearer"  # Tells the client what is expected.
    assert "content" not in response.get_json()  # No results in the body.


def test_401_happens_before_the_file_is_read(client, setup, monkeypatch):  # Acceptance: "without reading results".
    def forbidden(*_args, **_kwargs):  # Replacement that fails the test if it is ever called.
        raise AssertionError("results file was read before authentication")  # Loud failure.
    monkeypatch.setattr(Path, "read_text", forbidden)  # Any file read now fails the test.
    monkeypatch.setattr(Path, "stat", forbidden)  # Even checking the file size counts as touching it.
    assert client.get("/results").status_code == 401  # Still a clean 401.


# ------------------------------------------------- authorized requests ---

def test_authorized_request_returns_only_configured_file(client):  # Acceptance: correct file with credentials.
    response = client.get("/results", headers=AUTH)  # Authenticated request.
    assert response.status_code == 200  # Success.
    assert json.loads(response.get_json()["content"]) == RESULTS  # Same "content" string shape as before.


@pytest.mark.parametrize("path", [  # Old-style and traversal attempts.
    "/read_file/secret.txt", "/read_file/../secret.txt", "/read_file//etc/passwd",  # Old endpoint.
    "/results/../secret.txt", "/results?file=secret.txt", "/results/secret.txt",  # Tricks on the new endpoint.
])  # End of the parameter list.
def test_old_read_file_and_path_tricks_expose_nothing(client, setup, path):  # Acceptance: old URLs are dead.
    response = client.get(path, headers=AUTH)  # Even WITH a valid token.
    body = response.get_data(as_text=True)  # Raw body text.
    assert "do not leak" not in body and "root:" not in body  # No other file content.
    if response.status_code == 200:  # Only "/results?file=..." reaches the real endpoint...
        assert json.loads(response.get_json()["content"]) == RESULTS  # ...and it ignores the parameter.
    else:  # Everything else must be a generic 404.
        assert response.status_code == 404 and response.get_json() == {"error": "Not found"}  # Generic message.


def test_post_is_not_allowed(client):  # Only GET is offered.
    assert client.post("/results", headers=AUTH).status_code == 405  # Method not allowed.


# ---------------------------------------------- controlled error handling ---

def test_missing_results_file_gives_generic_503(client, setup):  # Acceptance: controlled error, no paths.
    setup["results"].unlink()  # Delete the results file.
    response = client.get("/results", headers=AUTH)  # Authenticated request.
    assert response.status_code == 503  # "Try later".
    assert response.get_json() == {"error": "Results unavailable"}  # Exactly this text, nothing else.
    assert str(setup["tmp"]) not in response.get_data(as_text=True)  # No folder names leaked.


def test_invalid_json_results_give_generic_500(client, setup):  # Acceptance: invalid results are rejected.
    setup["results"].write_text("{not json", encoding="utf-8")  # Break the file.
    response = client.get("/results", headers=AUTH)  # Authenticated request.
    assert response.status_code == 500 and response.get_json() == {"error": "Results unavailable"}  # Generic error.


def test_oversized_results_are_refused(client, setup):  # Protection against serving huge files.
    setup["results"].write_text("[" + "1," * 600_000 + "1]", encoding="utf-8")  # About 1.2 MB of valid JSON.
    assert client.get("/results", headers=AUTH).get_json() == {"error": "Results unavailable"}  # Refused.


def test_unexpected_exception_is_not_echoed(setup, monkeypatch):  # Raw exception text must never reach the client.
    settings = results_server.load_settings(setup["path"])  # Normal settings.
    app = results_server.create_app(settings)  # Normal app.
    monkeypatch.setattr(results_server.json, "loads", lambda _s: 1 / 0)  # Force a ZeroDivisionError inside the route.
    response = app.test_client().get("/results", headers=AUTH)  # Authenticated request.
    assert response.status_code == 500 and "division" not in response.get_data(as_text=True)  # Generic answer.


def test_every_response_disables_caching(client):  # Acceptance: prevent response caching.
    for response in (client.get("/results"), client.get("/results", headers=AUTH), client.get("/nope")):  # 401, 200, 404.
        assert "no-store" in response.headers["Cache-Control"]  # Present on all of them.


def test_debug_mode_is_off(setup):  # Flask's debugger must never be active.
    app = results_server.create_app(results_server.load_settings(setup["path"]))  # Build the app.
    assert app.debug is False  # Debug disabled.


# ---------------------------------------------------- settings checks ---

@pytest.mark.parametrize("change", [  # Each dictionary makes the settings unsafe in one way.
    {"host": "0.0.0.0"},  # Listening on every interface.
    {"token": "short"},  # Weak token.
    {"results_file": ""},  # No file configured.
    {"allow_plain_http": False},  # Plain HTTP without explicit opt-in.
    {"certfile": "cert.pem"},  # Certificate without key.
])  # End of the parameter list.
def test_unsafe_settings_refuse_to_start(setup, change):  # The server must not start with unsafe settings.
    data = json.loads(setup["path"].read_text(encoding="utf-8"))  # Load the good settings.
    data.update(change)  # Make them unsafe.
    setup["path"].write_text(json.dumps(data), encoding="utf-8")  # Save.
    with pytest.raises(results_server.SettingsError):  # Expect our own error type...
        results_server.load_settings(setup["path"])  # ...when loading them.


def test_init_creates_random_token(tmp_path, capsys):  # --init writes a fresh secret.
    path = tmp_path / "cfg.json"  # Target file.
    results_server.main(["--config", str(path), "--init", "--results-file", "r.json", "--host", "127.0.0.1"])  # Run --init.
    data = json.loads(path.read_text(encoding="utf-8"))  # Read what was written.
    assert len(data["token"]) >= 32 and data["token"] in capsys.readouterr().out  # Long token, printed once.


# ------------------------------------- standalone launch path (live HTTP) ---

def test_obsolete_flask_server_script_is_gone():  # The old standalone script must not come back.
    assert not (SCRIPTS / "Flask_server.py").exists()  # Only results_server.py may start a server.


def test_standalone_main_refuses_without_settings(tmp_path):  # Missing settings -> exit code 1, nothing served.
    assert results_server.main(["--config", str(tmp_path / "missing.json")]) == 1  # Clean failure.


def test_standalone_server_live_http(setup):  # "python results_server.py" for real: main() + real HTTP requests.
    settings = results_server.load_settings(setup["path"])  # Load settings (only to know the port).
    thread = threading.Thread(target=results_server.main, args=(["--config", str(setup["path"])],), daemon=True)  # Same as the command line.
    thread.start()  # Start main() in the background.
    base = f"http://127.0.0.1:{settings['port']}"  # Base URL.
    for _ in range(50):  # Wait up to 5 s until the server accepts connections.
        try:  # The first attempts may happen before the socket is open.
            requests.get(base + "/results", timeout=1)  # Any answer means the server is up.
            break  # Server is ready.
        except requests.exceptions.ConnectionError:  # Not ready yet.
            threading.Event().wait(0.1)  # Wait 0.1 s and try again.
    assert requests.get(base + "/results", timeout=5).status_code == 401  # No token -> 401.
    assert requests.get(base + "/read_file/" + str(setup["secret"]), headers=AUTH, timeout=5).status_code == 404  # Old URL dead.
    config = {"url": base + "/results", "token": TOKEN, "allow_plain_http": True}  # Robot client settings.
    assert json.loads(results_client.fetch_results(config)) == RESULTS  # Robot client gets the data.


def test_standalone_server_live_https(setup):  # HTTPS with certificate verification.
    pytest.importorskip("cryptography")  # Skip if the optional certificate library is missing.
    results_server.make_certificate(setup["path"], "127.0.0.1")  # Create cert + key and enable HTTPS in the settings.
    settings = results_server.load_settings(setup["path"])  # Reload settings (now with certfile/keyfile).
    server = results_server.build_server(settings)  # HTTPS server.
    run_live(server)  # Start it.
    try:  # Always stop the server afterwards.
        url = results_server.server_url(settings)  # https://127.0.0.1:<port>/results
        assert url.startswith("https://")  # HTTPS is active.
        config = {"url": url, "token": TOKEN, "ca_cert": settings["certfile"]}  # Robot trusts exactly this certificate.
        assert json.loads(results_client.fetch_results(config)) == RESULTS  # Verified HTTPS works.
        with pytest.raises(results_client.ResultsFetchError):  # Without our certificate...
            results_client.fetch_results({"url": url, "token": TOKEN, "ca_cert": None})  # ...verification must fail.
    finally:  # Clean-up.
        server.stop()  # Close the socket.


# --------------------------------------------- GUI launch path (live HTTP) ---

def import_gui(monkeypatch, setup):  # Import Normalization.py headless with our test settings.
    pytest.importorskip("qtpy")  # Skip if Qt is not installed.
    pytest.importorskip("pandas")  # Skip if pandas is not installed.
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")  # No real screen needed.
    monkeypatch.setenv("NORMATRONS_SERVER_CONFIG", str(setup["path"]))  # Point the GUI to the test settings.
    monkeypatch.chdir(setup["tmp"])  # So the GUI's relative config.json is looked up in the temp folder.
    import Normalization  # Import the GUI module.
    return Normalization  # Hand it to the test.


def test_gui_module_has_no_unrestricted_endpoint(monkeypatch, setup):  # The GUI cannot start the old server.
    gui = import_gui(monkeypatch, setup)  # Import the GUI.
    assert not hasattr(gui, "flask_app") and not hasattr(gui, "read_file")  # Old app and route are gone.


def test_gui_window_serves_restricted_endpoint(monkeypatch, setup):  # Same behavior when launched from the GUI.
    gui = import_gui(monkeypatch, setup)  # Import the GUI.
    from qtpy.QtWidgets import QApplication  # Qt application class.
    app = QApplication.instance() or QApplication([])  # One QApplication per process.
    window = gui.ResultsServerWindow()  # Exactly what "python Normalization.py --results-server" creates.
    try:  # Always stop the server afterwards.
        assert window.server is not None  # The server started.
        base = f"http://127.0.0.1:{json.loads(setup['path'].read_text())['port']}"  # Base URL.
        assert requests.get(base + "/results", timeout=5).status_code == 401  # No token -> 401.
        assert requests.get(base + "/read_file/" + str(setup["secret"]), headers=AUTH, timeout=5).status_code == 404  # Old URL dead.
        response = requests.get(base + "/results", headers=AUTH, timeout=5)  # Authenticated.
        assert json.loads(response.json()["content"]) == RESULTS  # Only the configured file.
    finally:  # Clean-up.
        window.close()  # Triggers closeEvent -> server.stop().
        app.processEvents()  # Let Qt handle the close.


def test_gui_window_refuses_unsafe_settings(monkeypatch, setup):  # Unsafe settings -> GUI does not serve.
    data = json.loads(setup["path"].read_text(encoding="utf-8"))  # Load settings.
    data["host"] = "0.0.0.0"  # Make them unsafe.
    setup["path"].write_text(json.dumps(data), encoding="utf-8")  # Save.
    gui = import_gui(monkeypatch, setup)  # Import the GUI.
    from qtpy.QtWidgets import QApplication  # Qt application class.
    app = QApplication.instance() or QApplication([])  # Keep a reference, otherwise Python deletes the Qt app at once.
    assert gui.ResultsServerWindow().server is None and app is not None  # No server object was started.


# ------------------------------------------------------- robot client ---

class FakeResponse:  # Minimal stand-in for a requests.Response.
    def __init__(self, status, body):  # Store status code and JSON body.
        self.status_code, self._body = status, body  # Remember both.

    def json(self):  # Mimic Response.json().
        if isinstance(self._body, Exception):  # Simulate a non-JSON body.
            raise self._body  # Raise like requests would.
        return self._body  # Return the parsed body.


class FakeHttp:  # Stand-in for the requests module that records the call.
    def __init__(self, result):  # result: a FakeResponse or an exception to raise.
        self.result, self.kwargs = result, None  # Remember what to return.

    def get(self, url, **kwargs):  # Mimic requests.get().
        self.kwargs = kwargs  # Record headers, timeout, verify...
        if isinstance(self.result, Exception):  # Simulate network failure.
            raise self.result  # Raise it.
        return self.result  # Return the fake response.


HTTP_CONFIG = {"url": "http://pc:5000/results", "token": TOKEN, "allow_plain_http": True}  # Client settings for tests.


def test_client_sends_token_timeout_and_no_redirects():  # Explicit timeout and auth header.
    http = FakeHttp(FakeResponse(200, {"content": "[]"}))  # Successful fake server.
    assert results_client.fetch_results(HTTP_CONFIG, http=http) == "[]"  # Returns the content text.
    assert http.kwargs["headers"]["Authorization"] == "Bearer " + TOKEN  # Token in the header, not the URL.
    assert http.kwargs["timeout"] == 10 and http.kwargs["allow_redirects"] is False  # Timeout + no redirects.


@pytest.mark.parametrize("result", [  # Every way the download can go wrong.
    FakeResponse(401, {"error": "Unauthorized"}),  # Wrong token.
    FakeResponse(503, {"error": "Results unavailable"}),  # File missing on the PC.
    FakeResponse(200, ValueError("not json")),  # Broken body.
    FakeResponse(200, {"content": 5}),  # Wrong type.
    requests.exceptions.ConnectTimeout("timed out"),  # Network timeout.
    requests.exceptions.ConnectionError("refused"),  # Server not running.
])  # End of the parameter list.
def test_client_raises_controlled_error(result):  # All failures -> ResultsFetchError without secrets.
    with pytest.raises(results_client.ResultsFetchError) as info:  # Expect our error type.
        results_client.fetch_results(HTTP_CONFIG, http=FakeHttp(result))  # Try to download.
    assert TOKEN not in str(info.value)  # The token never appears in the message.


@pytest.mark.parametrize("config", [  # Unsafe or outdated client settings.
    {"url": "http://pc:5000/read_file/x.json", "token": TOKEN, "allow_plain_http": True},  # Old endpoint.
    {"url": "http://pc:5000/results", "token": TOKEN},  # Plain HTTP without opt-in.
    {"url": "https://pc:5000/results", "token": TOKEN},  # HTTPS without certificate.
    {"url": "http://pc:5000/results", "allow_plain_http": True},  # No token.
])  # End of the parameter list.
def test_client_config_validation(tmp_path, config):  # The robot refuses bad settings before any request.
    path = tmp_path / "client.json"  # Temporary client settings file.
    path.write_text(json.dumps(config), encoding="utf-8")  # Save the bad settings.
    with pytest.raises(results_client.ResultsFetchError):  # Expect our error type.
        results_client.load_client_config(str(path))  # Loading must fail.


# ------------------------------------- robot protocol aborts before pipetting ---

def load_protocol_function(name, namespace):  # Extract one function from 1x_Norm_Protocol.py.
    tree = ast.parse((SCRIPTS / "1x_Norm_Protocol.py").read_text(encoding="utf-8"))  # Parse without running it.
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)  # Find the function.
    exec(compile(ast.Module(body=[node], type_ignores=[]), "protocol", "exec"), namespace)  # Define it in namespace.
    return namespace[name]  # Return the function object.


class FakeProtocol:  # Records everything the protocol does.
    def __init__(self):  # Start with an empty action log.
        self.actions = []  # List of (action, details).

    def comment(self, text):  # Mimic protocol.comment().
        self.actions.append(("comment", text))  # Record it.

    def __getattr__(self, name):  # Any other call (load_labware, load_instrument, ...) is "robot activity".
        def record(*args, **kwargs):  # Generic recorder.
            self.actions.append((name, args))  # Record the call.
        return record  # Return the recorder.


def test_protocol_aborts_before_any_labware_or_pipetting():  # Acceptance: robot aborts on retrieval failure.
    def failing_fetch(_config):  # Simulate a 401 from the server.
        raise results_client.ResultsFetchError("The results server rejected the token (HTTP 401).")  # Same error type.
    namespace = {  # Names the extracted functions expect to exist.
        "ResultsFetchError": results_client.ResultsFetchError,  # Real error class.
        "load_client_config": lambda: HTTP_CONFIG,  # Pretend the settings were loaded.
        "fetch_results": failing_fetch,  # Pretend the server rejected us.
        "protocol_api": type("api", (), {"ProtocolContext": object}),  # Only needed for the type hint of run().
    }  # End of namespace.
    load_protocol_function("get_file_content", namespace)  # Define get_file_content in the namespace.
    run = load_protocol_function("run", namespace)  # Define run() in the same namespace.
    protocol = FakeProtocol()  # Fake robot.
    with pytest.raises(results_client.ResultsFetchError):  # The run must stop with the error...
        run(protocol)  # ...when started.
    assert [a for a, _ in protocol.actions] == ["comment"]  # Only a log message; no labware, no pipette, no movement.


def test_protocol_has_no_hardcoded_file_path_or_old_endpoint():  # The robot no longer chooses a file.
    text = (SCRIPTS / "1x_Norm_Protocol.py").read_text(encoding="utf-8")  # Read the protocol source.
    assert "read_file" not in text and "C:/Users" not in text  # Old endpoint and PC path are gone.
