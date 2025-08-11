# Ensure project root (this directory) is on sys.path so 'app' package imports in tests
import sys, os
root = os.path.dirname(__file__)
if root not in sys.path:
    sys.path.insert(0, root)
