# Normatrons: DNA Normalization with the Opentrons OT-2

A Python-based workflow for calculating water additions from DNA concentration measurements and supplying those volumes to an Opentrons OT-2 liquid-handling robot.

Normatrons combines an Excel-reading desktop application, JSON-based data exchange, and an OT-2 protocol. The intended workflow supports one or two 96-position sample layouts.

## Project information

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

## Overview

Normatrons connects DNA concentration measurements to an automated water-addition workflow:

1. Import concentration measurements from Excel.
2. Enter a destination concentration and calculation factor.
3. Calculate water additions for each sample.
4. Inspect the results in a 96-position layout.
5. Export one or two datasets to JSON.
6. Make the results available to the OT-2 through a local HTTP service.
7. Use the robot protocol to add water to samples in temperature-controlled labware.

The software uses measurements that have already been generated. It does not analyze gel images or measure DNA concentration.

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
V_{\mathrm{water}} = \max\left( \left(\frac{C_{\mathrm{input}}}{C_{\mathrm{target}}} - 1\right)F + 10.1\right)
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

## Desktop workflow

1. Open `Normalization.py`.
2. Select “Open Excel File”.
3. Inspect the imported worksheet.
4. Confirm concentration units and sample order.
5. Enter the destination concentration and factor.
6. Leave “2nd gel” unchecked for the first dataset.
7. Select “Calculate!”.
8. Choose an output directory if prompted.
9. Inspect the displayed water additions and exported JSON.

### Processing a second dataset

For a second dataset:

1. Load its Excel workbook.
2. Select “2nd gel”.
3. Calculate and save the results.

In the normal one-/two-dataset workflow:

- With “2nd gel” unchecked, saving replaces the output with the current dataset.
- With “2nd gel” checked, saving retains the first dataset and appends or replaces the second.

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
