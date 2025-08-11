import sys, os
# Ensure project root on path for pytest discovery when pythonpath ini not applied early
root = os.path.dirname(__file__)
if root not in sys.path:
    sys.path.insert(0, root)
