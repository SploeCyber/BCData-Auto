import json
import requests

import sys

argv = sys.argv
if len(argv) < 2:
    print(
        "usage: python test_metadata.py <path/to/metadata.json> [country_code] [version]"
    )
    exit(1)

path = argv[1]

if len(argv) >= 3:
    cc_c = argv[2]
else:
    cc_c = None

if len(argv) >= 4:
    gv_c = argv[3]
else:
    gv_c = None


with open(path, "r") as f:
    metadata = json.loads(f.read())

base_url = metadata.get("base_url")
if base_url is None:
    print("Error: No `base_url` field!")
    exit(1)

if not isinstance(base_url, str):
    print("Error: `base_url` must be a string!")
    exit(1)

versions = metadata.get("versions")
if versions is None:
    print("Error: No `versions` field!")
    exit(1)

if not isinstance(versions, dict):
    print("Error: `versions` must be a map!")
    exit(1)

found = False
for cc, cc_versions in versions.items():
    if cc_c != cc and cc_c is not None:
        continue
    found = True
    if cc not in ["jp", "en", "kr", "tw"]:
        print(f"Error: {cc} is not a valid country code!. Expected jp, en, tw, or kr")
        exit(1)

    if not isinstance(cc_versions, dict):
        print(f"Error: versions for {cc} must be a map!")
        exit(1)

    found_gv = False
    for game_version, version in cc_versions.items():
        if game_version != gv_c and gv_c is not None:
            continue
        found_gv = True
        if not isinstance(version, str):
            print(f"Error: version field for {cc} for {game_version} is not a string!")
            exit(1)
        url = base_url + version

        resp = requests.head(url)
        if resp.status_code != 200:
            print(
                f"Error: response for url: {url} for {cc} for {game_version} returned {resp.status_code}, expected 200!"
            )
            exit(1)

        print(f"Success: {game_version}.{cc}")

    if not found_gv:
        print(f"Could not find game version: {gv_c}")
        exit(1)
    else:
        print(f"All successful for {cc}")


for cc in ["jp", "kr", "en", "tw"]:
    if cc not in versions:
        print(f"Error: missing versions for country code: {cc}!")
        exit(1)

if not found:
    print(f"Could not find cc: {cc_c}")
else:
    print("All successfull!")
