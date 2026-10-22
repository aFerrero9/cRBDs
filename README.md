# RBD & cRBD Reliability Evaluator

A Python-based tool for modeling, composing, and evaluating the reliability of complex systems using Reliability Block Diagrams (RBDs) and Colored Reliability Block Diagrams (cRBDs).

This tool parses plain text system definitions, builds algebraic systems compositions, and translates the topology into logic formulas (in DIMACS WCNF format) to calculate exact system unreliability using Weighted Model Counting (WMC) via the included GPMC solver.

## Requirements

* **Python 3.x**

* **Graphviz:** Required for generating visual PDFs of your c/RBDs (`pip install graphviz` and ensure the system binary is installed).

* *Note: The GPMC solver binary is already included in the repository (`./solvers/gpmc`), so no extra installation is required for it.*

## Usage

**Important:** You must execute the script from the **root directory** of the repository. This ensures that the generated diagrams and WCNF files are correctly saved in their respective `./diagrams/` and `./wmc_files/` folders.

Run the main script from your terminal:

```
python3 src/wmc_crbd.py <filepath> <mission_time> [--o]


```

### Arguments:

* `filepath`: Path to the `.txt` file containing your system definitions.

* `t` (mission time): A float representing the mission time used to calculate the failure probabilities ($F(t) = 1 - e^{-\lambda t}$).

* `--o` *(Optional)*: **Optimization flag.** When passed, the tool uses the **Tseitin Transformation** to generate the logic formula. This avoids Out-of-Memory (OOM) errors caused by path explosion in highly redundant/complex topologies. Highly recommended for large systems.

**Example:**

```
python3 src/wmc_crbd.py crbd_examples/satellites.txt 100 --o


```

## Input File Format

The tool uses a strictly sectioned plain text format. You can define one or multiple systems in a single file and compose them at the end.

Empty lines and comments starting with `#` are ignored.

### 1. System Definition

Each system block **must** begin with a name declaration, followed by three mandatory sections:

```
NAME = MySystem

@SYSTEM
TYPE = RBD  # Or 'cRBD' for colored diagrams

@NODES
# Format: node_id, failure_rate_lambda, [non_functional_flag]
# System components need exactly 2 items:
valveA, 0.001
valveB, 0.002

# Structural (non-functional) nodes need a 3rd flag (can be 'nf', 'n', 'notf', 'false', 'nonf'):
s, 0, nf
e, 0, nf

# these nodes are just START and END in the c/RBD. 
# Lambda must be 0 because structural nodes has no failure rate. It doesn't influence unreliability of the system, just needed for the parser to work properly)

@TOPOLOGY
# For standard RBDs:
s -> valveA
s -> valveB
valveA -> e
valveB -> e

# For cRBDs, specify the colors after a colon:
# s -> valveA : red
# s -> valveB: blue, red
# valveA -> e: red
# valveB -> e: blue, red

# colors can be tuples as well, e.g. (red,yellow)


```

*Note: The graph strictly requires a Start and End node. You can use aliases like `s, start, inicio, source,` and `e, end, fin, sink `as long as they have the non-functional flag (uppercase letters works too).*

### 2. Expression Block (`@EXP`)

This **must** be the final section of your file. It evaluates the defined systems using overloaded operators to generate the final composed topology. Each system is represented by its name defined in the beginning of each definition (NAME=…)

* `>>` : **Serial Composition**

* `//` : **Parallel Composition**

**Example:**

```
@EXP
(satelliteA // satelliteB) >> networkingSystem

(if the file has only one system definition, @EXP must be just the name of the system)
```

## Outputs

When you run the tool, it will automatically generate:

1. **Visual Diagram:** A PDF rendering of your parsed DAG topology in the `./diagrams/` folder.

2. **DIMACS File:** The `.wcnf` logic formula in the `./wmc_files/` folder.

3. **Terminal Output:** The exact Unreliability probability calculated by the solver.

## Example File

Here is a quick example of a complete colored RBD with two parallel subsystems:

```
NAME = satelliteA

@SYSTEM
TYPE = cRBD

@NODES
s, 0, nf
e, 0, nf
cameraA, 0.0001
laserA, 0.0001
laserB, 0.0001
antennaB, 0.01
antennaA, 0.1

@TOPOLOGY
s -> cameraA: red
cameraA -> laserA: red
cameraA -> antennaA: red
antennaA -> e: red
laserA -> laserB: red
laserB -> antennaB: red
antennaB -> e: red

NAME = satelliteB

@SYSTEM
TYPE = cRBD

@NODES
s, 0, nf
e, 0, nf
cameraB, 0.0001
laserB, 0.0001
laserA, 0.0001
antennaA, 0.1
antennaB, 0.01

@TOPOLOGY
s -> cameraB: blue
cameraB -> laserB: blue
cameraB -> antennaB: blue
antennaA -> e: blue
laserB -> laserA: blue
laserA -> antennaA: blue
antennaB -> e: blue

@EXP
satelliteA // satelliteB




```