# Normatrons: DNA Normalization with the Opentrons OT-2

A Python-based workflow for calculating water additions from DNA concentration measurements and supplying those volumes to an Opentrons OT-2 liquid-handling robot.

Normatrons combines an Excel-reading desktop application, JSON-based data exchange, and an OT-2 protocol. The intended workflow supports one or two 96-position sample layouts.

<details>
    
<summary> Project information </summary>

| Field | Description |
|---|---|
| Author | Jan Woyzichovski |
| Repository | https://github.com/JanWoyzi/Opentrons_OT2_Normalization |
| Software name | Normatrons / Opentrons_OT2_Normalization |
| Research domain | Molecular biology and laboratory automation |
| Programming language | Python |
| Input formats | Excel `.xlsx` and `.xls` |
| Intermediate format | JSON |
| Robot platform | Opentrons OT-2 |
| Declared protocol API | Opentrons Python Protocol API 2.13 |
| Software license | MIT |

This documentation describes the inspected source code and intended workflow. It does not constitute laboratory validation or a verified compatibility statement.
</details>

## Overview

Normatrons connects DNA concentration measurements to an automated water-addition workflow using a desktop computer and an Opentrons OT-2.

The desktop computer runs the normalization application and Flask server. The OT-2 runs the liquid-handling protocol through its built-in Jupyter Notebook access point.

The workflow is:

1. Upload `Scripts/1x_Norm_Protocol.py` to the OT-2 through its built-in Jupyter environment.
2. Prepare a notebook to load and execute the protocol, and configure the connection to the desktop computer.
3. Import concentration measurements into the desktop application.
4. Enter the destination concentration and calculation factor.
5. Calculate and inspect the water additions.
6. Save the required one or two datasets to `normalization_results.json`.
7. Start the Flask server on the desktop computer and leave it running.
8. Execute the prepared notebook on the OT-2 to start the protocol.
9. The protocol retrieves the saved results from the desktop computer and performs the water additions.

The software uses concentration measurements that have already been generated. It does not analyze gel images or measure DNA concentration.

The intended liquid-handling operation adds water directly to existing DNA samples. It does not transfer DNA into a separate destination plate.

## Repository structure

```text
Opentrons_OT2_Normalization/
├── LICENSE
├── README.md
└── Scripts/
    ├── Normalization.py
    ├── Flask_server.py
    ├── 1x_Norm_Protocol.py
    └── config.json
```

| File | Purpose |
|---|---|
| `Normalization.py` | Desktop GUI for Excel import, volume calculation, results display, JSON export, saved preferences, and integrated server launch. |
| `Flask_server.py` | Standalone Flask application for serving file contents to the robot. |
| `1x_Norm_Protocol.py` | OT-2 protocol intended to retrieve calculated volumes and dispense water. |
| `config.json` | Saved GUI settings, including paths, calculation parameters, and window dimensions. |
| `LICENSE` | Software licensing terms. |

## Requirements

### Desktop software

The application uses:

- Python.
- `qtpy` and a compatible Qt binding, such as `PyQt5`.
- `pandas`.
- `Flask`.
- `tabulate`.
- An appropriate Excel reader: `openpyxl` for typical `.xlsx` files or `xlrd` for legacy `.xls` files.

These requirements are inferred from the source. Tested Python and dependency versions should be recorded for each deployment.

### Robot software

The robot-side workflow requires:

- The Opentrons Python API.
- The `requests` package.
- Access to the required labware definitions.
- Network connectivity to the computer providing the results.

The protocol declares API level `2.13`. Confirm compatibility with the installed OT-2 software before use.

### Hardware

The configured workflow uses:

- An Opentrons OT-2.
- A P300 Single-Channel GEN2 pipette on the left mount.
- A P20 Single-Channel GEN2 pipette on the right mount.
- One Temperature Module GEN2 for the first dataset.
- A second Temperature Module GEN2 when processing two datasets.
- 20 µl and 200 µl filter-tip racks.
- A water-source tube block.
- Temperature-module-compatible sample labware.

## Installation

### Desktop computer

Clone the repository and create an isolated Python environment:

```bash
git clone https://github.com/JanWoyzi/Opentrons_OT2_Normalization.git  # Download the repository.
cd Opentrons_OT2_Normalization  # Enter the repository directory.
python -m venv .venv  # Create an isolated Python environment.
```

Activate the environment using the command appropriate for your operating system.

Install the desktop dependencies:

```bash
python -m pip install qtpy PyQt5 pandas Flask openpyxl xlrd tabulate  # Install the desktop dependencies and Excel readers.
```

Launch the application:

```bash
cd Scripts  # Use the scripts directory so relative configuration paths resolve there.
python Normalization.py  # Start the desktop application.
```

These commands provide a proposed setup based on the source imports. They are not a tested environment specification.

Before first use, review or remove the supplied `config.json`, which contains computer-specific settings.

### OT-2 and Jupyter preparation

The robot protocol is prepared and executed using the OT-2’s built-in Jupyter Notebook access point.

1. Connect to the OT-2 and open its Jupyter environment.
2. Upload `Scripts/1x_Norm_Protocol.py` to the robot.
3. Create or open the notebook used to prepare and execute the protocol.
4. Configure the desktop computer’s address and the location of `normalization_results.json` as required by the protocol.
5. Confirm that the notebook can access the uploaded protocol and that the required labware definitions are available.
6. Prepare the protocol-loading and execution cells, keeping robot execution separate from preparation.
7. Load the required labware, tips, water, and samples according to the deck layout.

The repository contains the Python protocol file; a ready-made execution notebook is not included in the documented repository structure.

Preparing or uploading the protocol does not start the normalization run. Execute the robot notebook only after the results have been saved, the Flask server is running, and the experimental setup has been checked.

## Input data

### Excel layout

The application reads the first worksheet. The first row supplies column headers, and the first data column is excluded from the calculation.

For the intended 96-position layout, prepare:

- Eight sample rows.
- Twelve numeric sample columns.
- One leading column for row labels or other information that should not be calculated.

Example structure:

| Row | 1 | 2 | … | 12 |
|---|---|---|---|---|
| A | Concentration | Concentration | … | Concentration |
| B | Concentration | Concentration | … | Concentration |
| C | Concentration | Concentration | … | Concentration |
| D | Concentration | Concentration | … | Concentration |
| E | Concentration | Concentration | … | Concentration |
| F | Concentration | Concentration | … | Concentration |
| G | Concentration | Concentration | … | Concentration |
| H | Concentration | Concentration | … | Concentration |

Use numeric values in the sample cells. Record units separately rather than adding unit strings to individual numeric cells.

The GUI labels the destination concentration in ng/µl; input concentrations should use compatible units.

### Sample-to-well mapping

Values are read down each sample column before moving to the next column:

```text
A1 → B1 → C1 → D1 → E1 → F1 → G1 → H1 → A2 → … → H12
```

Mapping follows worksheet position, not a lookup of sample identifiers. Confirm that the workbook order matches the physical sample arrangement.

Retain an independent sample-to-well map with the experimental record.

## Calculation

For each numeric measurement, the application implements:

```math
V_{\mathrm{water}} = \max\left(0, \left(\frac{C_{\mathrm{input}}}{C_{\mathrm{target}}} - 1\right)F + 10.1\right)
```

Positive results are rounded to one decimal place.

| Parameter | Meaning |
|---|---|
| `C_input` | Numeric concentration measurement from Excel. |
| `C_target` | Destination concentration entered in the GUI. |
| `F` | User-entered calculation factor. |
| `10.1` | Fixed additive offset in the implemented expression. |
| `V_water` | Result interpreted as a water addition in µl. |

This describes the implemented calculation, not a universal dilution equation.
Establish the experimental meaning and units of the factor and offset before
applying the workflow to another assay.

Record all calculation parameters with each experiment. Adding water cannot
increase the concentration of a sample below its target.

## Desktop workflow and robot execution

### 1. Calculate the first dataset

On the desktop computer:

1. Open `Normalization.py`.
2. Select “Open Excel File”.
3. Inspect the imported worksheet.
4. Confirm concentration units and sample order.
5. Enter the destination concentration and factor.
6. Leave “2nd gel” unchecked for the first dataset.
7. Select “Calculate!”.
8. Choose an output directory if prompted.
9. Inspect the displayed water additions and exported `normalization_results.json`.

### 2. Add a second dataset, if required

Before starting the robot:

1. Load the second Excel workbook.
2. Select “2nd gel”.
3. Calculate and save the results.
4. Confirm that the output contains both intended datasets in the correct order.

With “2nd gel” unchecked, saving replaces the output with the current dataset. With it checked, the normal one-/two-dataset workflow retains the first dataset and appends or replaces the second.

### 3. Start the Flask server on the desktop computer

After saving and checking all datasets:

1. Select “Flask Server” in the desktop application to launch the integrated server.
2. Leave the server process/window running.
3. Confirm that the configured results-file location matches the saved output.

Start the server before executing the robot notebook: the protocol needs it to retrieve the results at the beginning of the run.

Use only one server-launch method. The standalone `Flask_server.py` is an alternative, but its current approximately 10-second shutdown timer makes the timing of robot retrieval important.

### 4. Start the protocol from the robot notebook

With the results saved and the desktop Flask server running:

1. Return to the prepared notebook in the OT-2’s Jupyter environment.
2. Confirm the selected protocol, connection settings, dataset order, and physical deck arrangement.
3. Execute the notebook cells that start the protocol.
4. Monitor retrieval of the results and the subsequent robot execution.

Do not change or overwrite the results file between the final check and retrieval by the robot.

### Execution order at a glance

```text
Prepare the protocol and notebook on the OT-2
                    ↓
Calculate and save all datasets on the desktop
                    ↓
Start the desktop Flask server
                    ↓
Execute the prepared notebook on the OT-2
                    ↓
Retrieve results and perform water additions
```

### Water requirement display

The field labeled “Maximum Water Volume” displays the sum of additions for the current calculation.

The displayed tube estimate uses 1,800 µl per source tube. Independently verify the complete water requirement for the planned robot run, including both datasets where applicable.

## Output data

The application writes:

```text
normalization_results.json
```

The outer JSON array contains one or two datasets. Each complete dataset contains 96 water-addition volumes in the documented well order.

| Property | Convention |
|---|---|
| Format | JSON |
| Outer structure | Array of datasets |
| Intended dataset length | 96 entries |
| Volume unit | µl |
| Dataset order | First dataset, then optional second dataset |
| Precision | Positive calculated additions rounded to one decimal place |

Abbreviated structural illustration—not a complete or valid robot-input example:

```text
[
  [volume_A1, volume_B1, ..., volume_H12],
  [volume_A1, volume_B1, ..., volume_H12]
]
```

The current output does not embed sample identifiers, units, workbook provenance, calculation parameters, or software version. Preserve those separately alongside the JSON.

## Computer-to-robot communication

The Flask service makes results accessible through HTTP on port `5000`.

The current response contains a `content` field holding the requested file as text. The client must decode the response and then interpret the file contents.

Configure the computer address and results-file location for the actual deployment. The GUI output directory and robot-side file location must refer to the same results.

The repository provides two server-launch options:

- The integrated server launched from `Normalization.py`.
- The standalone `Flask_server.py`.

Do not start both on the same port. The standalone implementation includes an approximately 10-second automatic shutdown timer.

Use an appropriately restricted laboratory connection. Do not expose the local file-serving service to the public internet.

## OT-2 configuration

### Deck layout

| Slot | Equipment |
|---|---|
| 3 | First Temperature Module GEN2 and sample labware |
| 4 | Water-source tube block |
| 6 | Optional second Temperature Module GEN2 and sample labware |
| 7 | Additional 200 µl filter-tip rack for two-dataset operation |
| 8 | Additional 20 µl filter-tip rack for two-dataset operation |
| 10 | First 200 µl filter-tip rack |
| 11 | First 20 µl filter-tip rack |

### Labware identifiers

```text
opentrons_96_filtertiprack_200ul
opentrons_96_filtertiprack_20ul
sarstedtsafeseal_24_aluminumblock_2000ul
nest0.2mlpcr8striptubes_96_aluminumblock_200ul
```

Confirm that the definitions are available and correspond to the physical equipment.

### Intended liquid-handling behavior

The protocol is intended to:

- Maintain sample modules at 4 °C during dispensing.
- Skip additions of 0.5 µl or less.
- Use the P20 for additions above 0.5 µl through 20 µl.
- Use the P300 for additions above 20 µl.
- Use a fresh P20 tip per destination.
- Reuse a P300 tip across larger additions.
- Advance through water-source tubes using a cumulative-volume counter.

Review these choices against the assay’s contamination requirements, pipetting limits, sample volumes, and labware geometry.

This description does not establish that the checked-in protocol is operational or experimentally validated. Simulate the intended configuration and perform a water-only trial before processing samples.

## Reproducibility and provenance

For each experiment, retain:

| Category | Information to preserve |
|---|---|
| Measurements | Original workbook, measurement method, instrument, units, and relevant calibration. |
| Sample identity | Sample-to-well mapping and dataset order. |
| Calculation | Target concentration, factor, and applicable calculation assumptions. |
| Robot input | The exact JSON supplied to the robot. |
| Software | Git commit or release, Python version, dependency versions, and robot-software/API versions. |
| Hardware | Pipettes, tips, labware definitions, offsets, starting volumes, and deck arrangement. |
| Execution | Date, operator, simulation output, robot logs, and manual deviations. |

Store these records under a shared experiment identifier.

Apply appropriate access controls to sensitive sample information. The software license does not automatically determine reuse permissions for experimental data.

## Citation

Until an archival software citation is available, use this template:

> Woyzichovski, Jan. Normatrons: Opentrons_OT2_Normalization. GitHub repository. Version or commit: [exact release or commit]. https://github.com/JanWoyzi/Opentrons_OT2_Normalization. Accessed [YYYY-MM-DD].

Replace the bracketed fields with the version and access date actually used.

For a research release:

- Add a `CITATION.cff` file containing verified author and software metadata.
- Create a versioned release.
- Archive that release with a service providing a persistent identifier.
- Update the citation with the resulting identifier.

Do not substitute a repository URL or commit hash for an archival DOI.

## FAIR-oriented research software

This documentation supports discovery, access, interoperability, and reuse. It does not claim that the repository already satisfies every FAIR4RS requirement.

| Principle | Information provided | Further publication work |
|---|---|---|
| Findable | Name, author, repository, domain, keywords, and citation guidance. | Machine-readable citation metadata, persistent identifier, versioned releases, and indexing. |
| Accessible | Repository location, installation instructions, and deployment requirements. | Long-term archived software and metadata, with documented access conditions. |
| Interoperable | File formats, units, well order, dependencies, and hardware interfaces. | Versioned schemas, dependency specifications, and required labware definitions. |
| Reusable | License, workflow, parameter descriptions, provenance guidance, and version identification. | Tested environments, example inputs and outputs, and validation evidence. |

## Support and contributions

Use the repository’s GitHub Issues section for questions and proposed improvements.

When reporting behavior, include:

- The relevant commit or release.
- Operating system and dependency versions.
- Robot-software/API versions where applicable.
- A minimal anonymized input example.
- Expected and observed behavior.

Do not publish credentials or confidential sample information.

Contributions should document changes to calculation assumptions, file formats, sample ordering, hardware configuration, and dependencies.

## License

This software is distributed under the MIT License.

Copyright © 2026 JanWoyzi.

See `LICENSE` for the full terms, including attribution requirements and warranty provisions.
