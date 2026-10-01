import sys
from pathlib import Path

# Lets tests import oracle.py, which loads the reference model's numpy evaluator.
sys.path.insert(0, str(Path(__file__).parent))
