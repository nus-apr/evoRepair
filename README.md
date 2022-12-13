# java-coevolution
Prototype for co-evolution based Repair for Java

#### Building Docker
```commandline
git submodule update --init --recursive --remote && docker build -t evorepair .
```

#### Running a Container
```commandline
bash container
```

#### Testing EvoRepair Command
```commandline
evoRepair --help
```

#### Running test example
```commandline
evorepair --config test/leap_year/config.json
```
