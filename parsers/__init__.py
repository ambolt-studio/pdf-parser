import re
from .base import GenericParser
from .ifb import IFBParser
from .valley import ValleyParser
from .mercury import MercuryParser
from .pnb import PNBParser
from .wf import WFParser
from .citi import CitiParser
from .truist import TruistParser   # <-- nuevo

# Registramos CLASES, no instancias
REGISTRY = {
    "generic": GenericParser,
    "ifb": IFBParser,
    "valley": ValleyParser,
    "mercury": MercuryParser,
    "pnb": PNBParser,
    "wf": WFParser,
    "citi": CitiParser,
    "truist": TruistParser,       # <-- nuevo
}

# Patrones para detectar banco en el texto
DETECTION = [
    ("ifb", [
        r"International\s+Finance\s+Bank",
        r"\bIFB Bus Checking\b",
        r"\bifbbank\.com\b"
    ]),
    ("valley", [
        r"\bValley\b",
        r"Valley National Bank",
        r"\bvalley\.com\b"
    ]),
    ("mercury", [
        r"\bMercury\b",
        r"Choice Financial Group",
        r"help@mercury\.com"
    ]),
    ("pnb", [
        r"Pacific National Bank",
        r"\bP\.O\. Box 012620, Miami\b",
        r"\bACCT ENDING\b"
    ]),
    ("wf", [
        r"\bWells Fargo\b",
        r"wellsfargo\.com",
        r"\bWT\s"
    ]),
    ("citi", [
        r"\bCitiBusiness\b",
        r"\bCitibank\b",
        r"\bCiti\b"
    ]),
    ("truist", [                  # <-- nuevo
        r"\bTruist\b",
        r"truist\.com",
        r"\bBBT\d+\b"
    ]),
]

def detect_bank_from_text(full_text: str) -> str:
    """Detecta el banco a partir del texto del PDF."""
    if not full_text:
        return "generic"
    t = full_text[:20000]  # limitamos para performance
    for key, pats in DETECTION:
        if any(re.search(p, t, flags=re.I) for p in pats):
            return key
    return "generic"

