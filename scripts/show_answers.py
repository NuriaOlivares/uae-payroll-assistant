import glob, json, sys
f = sorted(glob.glob("evals/results/run-*.json"))[-1]
for r in json.load(open(f)):
    if r["id"] in sys.argv[1:]:
        print(r["id"], "->", r["answer"], "\n")