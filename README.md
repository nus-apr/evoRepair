# EvoRepair: Repurposing EvoSuite for Program Repair

## Instroduction

This tool uses EvoSuite so evolve both a patch pool and a test suite to find high-quality patches for program bugs.

## Requirements and Setup

### Docker (Recommended)

Dockerfile is recommended. Simply run

```
docker build -t evorepair .
docker run -it -d --name evo evorepair /bin/bash
```

and EvoRepair will have been set up.

### Local Machine

The following dependencies need to be installed:

* python 3.8+, and pip module `unidiff`
* JDK 8 (only tested on azul JDK 8.0.352)
* Maven 3.6.3
* Ant 1.0.13
* dos2unix
* Defects4J. `defects4j` needs to be on `PATH`. Also, `defects4j.diff` needs to be applied to the Defects4j directory (`patch -d /path/to/d4j -p1 -i /path/to/defects4j.diff`)

With all the dependencies, run

```
./setup.sh
```

## Usage

To repair a subject with the default config, run

```
python3 Repair.py -d --config d4j-subjects/chart_1_instr/config.json
```

An output directory would be created in `output/`.

For more parameters, see

```
python3 Repair.py --help
```

## Experiment Reproduction

Each subject in `d4j-subjects` was run 10 times, with the random seeds 100, 200, ..., 1000, respectively. The convenience script `run.py` was used to run the experiments.

To run a subject with a particular seed, e.g., lang_19_instr with seed 500, run

```
mkdir reproduction
./run.py reproduction lang_19_instr,500
```

Note that the output directory, in this case `reproduction`, needs to be 
created beforehand.

The script can also take multiple tasks, e.g.,

```
./run.py reproduction chart_1_instr,100 math_2_instr,200
```

## Output Structure

For an example output, see `example-output/math_95_instr`. The major directories are:

* `perfect-patches`: hall-of-fame patches that pass both the developer test suite and additionally generated test cases
* `plausible-patches`: plausible patches that pass the developer test suite
* `repair/genX/test-adequate`: patches that pass all the tests provided in the X-th generation
* `repair/genX/valid`: valid patch seeds found in genX, i.e., patches that pass the failing developer test cases but fail any other test case
* `statistics/statistics.csv`: per-generation statistics of plausible patches, killing tests, etc.