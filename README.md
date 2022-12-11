# java-coevolution
Prototype for co-evolution based Repair for Java

#### Building Docker
```commandline
docker build -t evorepair --build-arg SSH_KEY="$(cat ~/.ssh/id_rsa)" .
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
