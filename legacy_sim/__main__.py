"""Run the legacy simulator, or export the seed dataset.

    python -m legacy_sim                 # serve on http://127.0.0.1:8080
    python -m legacy_sim --port 9090
    python -m legacy_sim --export DIR    # write seed JSON for other
                                         # implementations (e.g. Spring Boot)
"""

import argparse
import json
import os

from legacy_sim.seed import build_dataset, dataset_digest


def export(directory):
    data = build_dataset()
    os.makedirs(directory, exist_ok=True)
    for key in ("services", "incidents", "change_requests", "stories",
                "deployments", "metrics"):
        with open(os.path.join(directory, f"{key}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(data[key], f, indent=1)
    with open(os.path.join(directory, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump({"generated_at": data["generated_at"], "seed": data["seed"],
                   "digest": dataset_digest(data),
                   "counts": {k: len(data[k]) for k in data
                              if isinstance(data[k], list)}}, f, indent=1)
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--export", metavar="DIR",
                        help="write the seed dataset as JSON and exit")
    args = parser.parse_args(argv)
    if args.export:
        print(f"Wrote seed dataset to {export(args.export)}")
        return
    import uvicorn

    from legacy_sim.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
