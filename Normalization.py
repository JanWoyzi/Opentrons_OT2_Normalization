from sys import argv, exit, executable
from os.path import exists, join
from json import load, dump
from qtpy.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog,
                            QTextEdit, QLabel, QLineEdit, QFormLayout, QCheckBox, QSizePolicy)
from qtpy.QtGui import QDoubleValidator, QFont
from pandas import read_excel, DataFrame, notna
from math import ceil
from flask import Flask, jsonify # request
from threading import Thread
from os import spawnl, P_NOWAIT

CONFIG_FILE = "config.json"  # File to store the last used file path and window size

# Flask Application
flask_app = Flask(__name__)

@flask_app.route('/read_file/<path:filename>')
def read_file(filename):
    try:
        with open(filename, 'r') as file:
            content = file.read()
        return jsonify({"content": content})
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def start_flask():
    """Start Flask server."""
    flask_app.run(host='0.0.0.0', port=5000, use_reloader=False)

class FlaskWindow(QMainWindow):
    """A minimal window to indicate Flask is running."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flask Server")
        self.setGeometry(200, 200, 300, 150)

        layout = QVBoxLayout()
        label = QLabel("Flask Server is running...", self)
        label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(label)

        central_widget = QWidget(self)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

# Function to start Flask in a separate process
def run_flask_server():
    """Run Flask server in a new process using sys.executable."""
    spawnl(P_NOWAIT, executable, executable, __file__, "--flask-server")


class NormalizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # self.last_file_path = None
        # self.save_dir = None
        self.setWindowTitle("Normatrons by Jan Woyzichovski, 2025")
        self.setGeometry(100, 100, 600, 400)

        # Initialize main layout
        layout = QVBoxLayout()

        # Button to open file explorer
        self.open_button = QPushButton("Open Excel File")
        self.open_button.clicked.connect(self.open_file_dialog)
        layout.addWidget(self.open_button)

        # Create central widget and a layout for the entire window
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)

        # Add the button at the top
        central_layout.addWidget(self.open_button)

        # Text area to display data (Excel file)
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        central_layout.addWidget(self.text_area)

        # Debug Line:
        self.debug_line = QLabel()
        self.debug_line.setFixedHeight(50)
        central_layout.addWidget(self.debug_line)

        # Results area to display data
        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_area.hide()

        # Create a horizontal layout for the form and the button
        form_and_button_layout = QHBoxLayout()

        # Form layout for labels and QLineEdits
        form_layout = QFormLayout()

        # Create destination concentration QLineEdit
        self.dest_concentration = QLineEdit()
        self.dest_concentration.setFixedHeight(20)  # Height of one line
        self.dest_concentration.setFixedWidth(80)  # Width for 6 digits
        self.dest_concentration.setValidator(QDoubleValidator())  # Allow only float values
        h_layout1 = QHBoxLayout()  # Horizontal layout for this row
        h_layout1.addWidget(self.dest_concentration)
        additional_label1 = QLabel("ng/µl")  # Additional text
        h_layout1.addWidget(additional_label1)
        form_layout.addRow("Destination Concentration:", h_layout1)

        # Create factor QLineEdit
        self.factor = QLineEdit()
        self.factor.setFixedHeight(20)
        self.factor.setFixedWidth(80)
        self.factor.setValidator(QDoubleValidator())  # Allow only float values
        h_layout2 = QHBoxLayout()  # Horizontal layout for this row
        h_layout2.addWidget(self.factor)
        additional_label2 = QLabel("x")
        h_layout2.addWidget(additional_label2)
        form_layout.addRow("Factor:", h_layout2)

        # Create maximum water volume QLineEdit
        self.max_water = QLineEdit()
        self.max_water.setFixedHeight(20)
        self.max_water.setFixedWidth(80)
        self.max_water.setReadOnly(True)
        self.max_water.setValidator(QDoubleValidator())  # Allow only float values
        h_layout3 = QHBoxLayout()  # Horizontal layout for this row
        h_layout3.addWidget(self.max_water)
        self.additional_label3 = QLabel("µl")
        h_layout3.addWidget(self.additional_label3)
        form_layout.addRow("Maximum Water Volume:", h_layout3)

        checkbox_and_button_layout = QHBoxLayout()
        self.second_gel_checkbox = QCheckBox("2nd gel")
        checkbox_and_button_layout.addWidget(self.second_gel_checkbox)

        # Create "Calculate!" button
        self.calculate_button = QPushButton("Calculate!")
        self.calculate_button.setFixedHeight(80)
        self.calculate_button.setFixedWidth(100)
        self.calculate_button.clicked.connect(self.calculate)
        checkbox_and_button_layout.addWidget(self.calculate_button)

        # Create "Flask Server" button
        self.Flask_Server_button = QPushButton("Flask Server")
        self.Flask_Server_button.setFixedHeight(80)
        self.Flask_Server_button.setFixedWidth(100)
        self.Flask_Server_button.clicked.connect(self.start_flask_server)
        checkbox_and_button_layout.addWidget(self.Flask_Server_button)

        # Add the form layout and the button layout into the HBox
        form_and_button_layout.addLayout(form_layout)
        form_and_button_layout.addLayout(checkbox_and_button_layout)  # Add the button next to the form layout

        # Add the form layout to the central layout
        central_layout.addLayout(form_and_button_layout)
        central_layout.addWidget(self.result_area)
        self.setCentralWidget(central_widget)
        self.load_config()

        self.extracted_data = None

    def open_file_dialog(self):
        # Open file dialog starting with the last used file path, if available
        start_path = self.last_file_path
        file_path, _ = QFileDialog.getOpenFileName(self, "Select an Excel File", start_path, "Excel Files (*.xlsx *.xls)")
        if file_path:
            # Save the selected file path
            self.last_file_path = file_path
            self.extract_data(file_path)

    def extract_data(self, file_path):
        try:
            df = read_excel(file_path, sheet_name=0, skiprows=0)
            df = df.fillna("")
            self.extracted_data = df
            formatted_table = df.to_markdown(index=False, tablefmt="tsv")
            self.text_area.setText(formatted_table)

        except Exception as e:
            self.debug_line.setText(f"Error reading the file: {e}")

    def calculate(self):
        if self.extracted_data is not None:
            try:
                # Read the destination concentration and factor from the QLineEdits
                dest_concentration_value = float(
                    self.dest_concentration.text()) if self.dest_concentration.text() else 1.0
                factor_value = float(self.factor.text()) if self.factor.text() else 1.0

                results = []
                for column_name, column in self.extracted_data.iloc[:, 1:].items():
                    for cell_value in column:
                        try:
                            if notna(cell_value):  # Check if the value is not NaN
                                result = (((float(cell_value) / dest_concentration_value) - 1) * factor_value) + 10.1
                                if result <= 0:
                                    results.append(0)
                                else:
                                    results.append(round(result, 1))
                            else:
                                results.append("NaN")
                        except ValueError:
                            results.append("NaN")  # Handle non-numeric values by appending "NaN"

                # Set the sum to the 'maximum water volume' field (self.max_water)
                self.max_water.setText(f"{sum(results):.1f}")  # Format to 1 decimal places
                self.additional_label3.setText(f"µl --> {ceil(sum(results)/1800)}x 2ml Epis will be necessary!")
                self.save_results_to_json(results)

                # Create the DataFrame with 8 columns (A to H) instead of 12
                results_df = DataFrame(
                    [results[i:i + 8] for i in range(0, len(results), 8)],
                    columns=[chr(65 + i) for i in range(8)]  # A to H
                )

                # Transpose the DataFrame to swap rows and columns
                results_df = results_df.T

                # Define the column names (1 to 12)
                column_names = [str(i) for i in range(1, 13)]
                results_df.columns = column_names

                # Convert the DataFrame to markdown
                formatted_table = results_df.to_markdown(index=True, tablefmt="tsv")

                # Add padding to the table cells to simulate centering
                formatted_table = "\n".join(
                    ["|".join([cell.center(8) if i > 0 else cell.ljust(8) for i, cell in enumerate(row.split("|"))])
                     for row in formatted_table.split("\n")]
                )
                if not self.result_area.isVisible():
                # Set the formatted results in the QTextEdit widget
                    window_height = self.height() + self.text_area.height()
                    self.resize(self.width(), window_height)
                    self.result_area.show()
                self.result_area.setText(formatted_table)

            except Exception as e:
                self.debug_line.setText(f"Error calculating: {e}")
        else:
            self.debug_line.setText("No data available. Please load an Excel file first.")

    def load_config(self):
        """Load all configuration data from the config file."""
        if exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                self.config_data = load(f)
        else:
            self.config_data = {}

        # Set values from the config file
        self.dest_concentration.setText(self.config_data.get("dest_concentration", ""))
        self.factor.setText(self.config_data.get("factor", ""))
        self.resize(self.config_data.get("window_size", {"width": 800, "height": 600}).get("width", 800),
                    self.config_data.get("window_size", {"width": 800, "height": 600}).get("height", 600))
        self.last_file_path = self.config_data.get("last_file_path", "")
        self.save_dir = self.config_data.get("save_directory", "")

    def save_config(self):
        """Save all configuration data to the config file."""
        config_data = {
            "window_size": {"width": self.width(), "height": self.height() - self.result_area.height()},
            "last_file_path": self.last_file_path,
            "dest_concentration": self.dest_concentration.text(),
            "factor": self.factor.text(),
            "save_directory": self.save_dir
        }
        with open(CONFIG_FILE, "w") as f:
            dump(config_data, f)

    def closeEvent(self, event):
        self.save_config()  # Save all configurations when the app is closed
        event.accept()

    def save_results_to_json(self, results):
        """Save results to a JSON file in the user-specified directory."""
        if not self.save_dir or not exists(self.save_dir):
            # Prompt the user to select a directory if none is set
            self.save_dir = QFileDialog.getExistingDirectory(self, "Select Directory to Save Results")
            if not self.save_dir:  # If no directory is selected, return early
                self.debug_line.setText("No directory selected for saving results.")
                return

            # Save the selected directory to the config
            self.save_config()  # Ensure the selected directory is saved to the config file

        # Save the results to a file in the specified directory
        save_path = join(self.save_dir, "normalization_results.json")
        try:
            if exists(save_path):
                with open(save_path, "r") as f:
                    data = load(f)
                if isinstance(data, list):
                    if self.second_gel_checkbox.isChecked():  # New functionality: Append second gel results
                        if len(data) >= 2:
                            data.pop()
                        data.append(results)
                    else:
                        data = [results]  # Overwrite if checkbox is not checked
                else:
                    data = [data, results] if self.second_gel_checkbox.isChecked() else [results]
            else:
                data = [results]
            with open(save_path, "w") as f:
                dump(data, f)
            self.debug_line.setText(f"Results successfully saved to:\n{save_path}")
        except Exception as e:
            self.debug_line.setText(f"Error saving results: {e}")

    def start_flask_server(self):
        """Start Flask server in a separate process with a minimal window."""
        run_flask_server()

# Main application loop
# Detect if running as a Flask server process
if __name__ == "__main__":
    if "--flask-server" in argv:
        app = QApplication(argv)
        font = QFont("Arial", 12)  # Set to the desired font and size
        app.setFont(font)
        flask_window = FlaskWindow()
        flask_window.show()

        # Start Flask in a new thread inside this window
        flask_thread = Thread(target=start_flask, daemon=True)
        flask_thread.start()

        exit(app.exec_())
    else:
        app = QApplication(argv)
        font = QFont("Arial", 12)  # Set to the desired font and size
        app.setFont(font)
        window = NormalizerApp()
        window.show()
        exit(app.exec_())