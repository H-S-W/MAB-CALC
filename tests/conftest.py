"""
Gor src/ importerbart for testerna.

De aldre testfilerna gor samma sys.path-insattning inline. Den har filen
gor det en gang for alla, sa att nya tester kan importera rakt.
"""

import sys
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
