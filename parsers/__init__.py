import re
from .base import GenericParser
from .ifb import IFBParser
from .valley import ValleyParser
from .mercury import MercuryParser
from .pnb import PNBParser
from .wf import WFParser
from .citi import CitiParser
from .truist import TruistParser
from .bofa import BOFAParser
from .chase import ChaseParser
# Si añadiste bofa_relationship.py, descomenta estas dos líneas:
# from .bofa_relationship import BOFARelationshipParser

# Registramos CLASES, no instancias
REGISTRY = {
    "generic": GenericParser,
    "ifb": IFBParser,
    "valley": ValleyParser,
    "mercury": MercuryParser,
    "pnb": PNBParser,
    "wf": WFParser,
    "citi": CitiParser,
    "truist": TruistParser,
    "bofa": BOFAParser,
    # "bofa_relationship": BOFARelationshipParser,  # si lo agregaste
    "chase": ChaseParser,
}

# Patrones para detectar banco en el texto - ORDEN IMPORTANTE
DETECTION = [
    # --- BOFA primero (para no confundir wires que mencionan JPMorgan Chase) ---
    ("bofa", [
        r"\bBank of America\b",
        r"bankofamerica\.com",
        r"\bBOFA\b",
        r"\bBusiness Advantage\b",
        r"1\.888\.BUSINESS"
    ]),

    # Si tenés un parser separado para Relationship, ponelo ANTES del BOFA genérico
    # ("bofa_relationship", [
    #     r"\bBusiness Advantage Relationship Banking\b",
    #     r"\bPreferred Rewards for Bus\b",
    #     r"\bcontinued on the next page\b",
    #     r"Your checking account\s+Deposits and other credits",
    # ]),

    # --- Chase después y con patrones más “de statement” (no de descripciones de wires) ---
    ("chase", [
        r"chase\.com",
        r"\bChase Mobile\b",
        r"\bChase Debit Card\b",
        r"\bChase Total Checking\b",
        r"\bChase Savings\b",
        # OJO: evitamos patrones genéricos como "JPMorgan Chase Bank" o "Chase Bank"
        # porque aparecen dentro de las descripciones de wires de otros bancos
    ]),

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
        r"\bNavigate Business Checking\b",
        r"\bInitiate Business Checking\b"
    ]),
    ("citi", [
        r"\bCitiBusiness\b",
        r"\bCitibank\b",
        r"\bCiti\b"
    ]),
    ("truist", [
        r"\bTruist\b",
        r"truist\.com",
        r"\bZELLE BUSINESS PAYMENT\b"
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
