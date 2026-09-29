import json
import sys


DUMMY_SECRET = "AR_TEST_PRIVATE_VALUE_82754"
sys.stdout.write("x" * 65530 + DUMMY_SECRET + "\n")
print("@@RUNNER " + json.dumps({"event": "stage", "value": DUMMY_SECRET}), flush=True)
print(DUMMY_SECRET, file=sys.stderr, flush=True)
