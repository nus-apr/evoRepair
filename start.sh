#!/usr/bin/env bash
set -x

if [ ! "$#" -eq 1 ]; then
	>&2 printf '%s\n' "Expected random seed"
	exit 1
fi

seed="$1"

BUGS=(math_95_instr lang_59_instr chart_1_instr math_50_instr math_70_instr math_73_instr)

for bug in ${BUGS[@]}; do
	./run_ablation.py new-ablation "$bug,$seed" &
	sleep 8
done

set +x
