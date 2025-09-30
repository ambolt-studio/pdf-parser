import re
from typing import List, Dict, Any, Optional
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    RE_AMOUNT,
    parse_mmdd_token,
    parse_long_date,
    parse_mmmdd,
)

class ChaseParser(BaseBankParser):
    key = "chase"
    
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []
        
        current_section = None
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue

            section_detected = self._detect_section(line)
            if section_detected:
                current_section = section_detected
                i += 1
                continue

            if self._is_basic_noise(line):
                i += 1
                continue

            date = self._extract_date(line, year)
            if not date:
                i += 1
                continue

            transaction_block = [line]
            j = i + 1
            lines_without_content = 0
            while j < len(lines):
                next_line = lines[j]
                if self._extract_date(next_line, year) or self._is_section_header(next_line):
                    break
                if next_line.strip() and not self._is_basic_noise(next_line):
                    transaction_block.append(next_line)
                    lines_without_content = 0
                else:
                    lines_without_content += 1
                    if lines_without_content >= 2:
                        break
                j += 1

            transaction = self._process_transaction_block(
                transaction_block, date, current_section, year
            )
            if transaction:
                results.append(transaction)

            i = j

        return results

    def _detect_section(self, line: str) -> Optional[str]:
        line_lower = line.lower().strip()
        if any(pattern in line_lower for pattern in [
            "depósitos y adiciones", "deposits and additions"
        ]):
            return "deposits"
        if any(pattern in line_lower for pattern in [
            "retiros electrónicos", "electronic withdrawals",
            "retiros electrÃ³nicos"
        ]):
            return "withdrawals"
        if line_lower in ("cargos", "charges"):
            return "fees"
        if any(pattern in line_lower for pattern in [
            "atm & debit card withdrawals", 
            "atm and debit card withdrawals",
            "card purchases"
        ]):
            return "withdrawals"
        return None

    def _is_section_header(self, line: str) -> bool:
        return self._detect_section(line) is not None

    def _is_basic_noise(self, line: str) -> bool:
        line_lower = line.lower().strip()
        if "*start*" in line_lower or "*end*" in line_lower:
            return True
        basic_noise = [
            "jpmorgan chase bank","página","page",
            "número de cuenta","account number",
            "total de depósitos","total deposits",
            "total de retiros","total withdrawals",
            "total comisiones","total fees",
            "saldo inicial","beginning balance",
            "saldo final","ending balance",
            "duplicate statement","customer service information",
            "checking summary","how to avoid the monthly service fee",
            "daily ending balance"
        ]
        if any(line_lower.startswith(pattern) for pattern in basic_noise):
            return True
        if re.match(r"^\s*\$[\d,]+\.\d{2}\s*$", line):
            return True
        if re.match(r"^\s*\d{12,}\s*$", line):
            return True
        if line_lower.startswith("en caso de errores") or line_lower.startswith("in case of errors"):
            return True
        return False

    def _extract_date(self, line: str, year: int) -> Optional[str]:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        legal_markers = [
            "llámenos al","call us at",
            "en caso de errores","in case of errors",
            "prepárese","prepare to provide",
        ]
        if any(marker in line_lower for marker in legal_markers):
            return None
        m = re.match(r"^(\d{1,2})/(\d{1,2})(?:\s|$)", line_stripped)
        if not m:
            return None
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            return f"{year:04d}-{mm:02d}-{dd:02d}"
        return None

    def _process_transaction_block(
        self, block: List[str], date: str, section_context: Optional[str], year: int
    ) -> Optional[Dict[str, Any]]:
        if not block:
            return None
        full_text = " ".join(s.strip() for s in block if s).strip()
        if not full_text:
            return None
        if self._contains_legal_content(full_text) or self._is_daily_balance_entry(full_text):
            return None
        amount = self._extract_amount_from_block_improved(block, full_text)
        if amount is None:
            return None
        description = self._clean_description(full_text)
        if not description or len(description) < 3:
            return None
        direction = self._determine_direction(description, section_context or "", amount, full_text)
        return {
            "date": date,
            "description": description,
            "amount": amount,
            "direction": direction
        }

    def _is_daily_balance_entry(self, text: str) -> bool:
        t = text.lower()
        if "daily ending balance" in t:
            return True
        if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\s+through\s+", t):
            if not any(x in t for x in ("payment","deposit","transfer","purchase","withdrawal","fee")):
                return True
        return False

    def _contains_legal_content(self, text: str) -> bool:
        t = text.lower()
        indicators = [
            "llámenos al 1-866-564-2262","call us at 1-866-564-2262",
            "en caso de errores o preguntas","in case of errors or questions",
            "prepárese para proporcionarnos","be prepared to give us"
        ]
        if any(s in t for s in indicators):
            return True
        if len(text) > 500 and re.search(r"1-\d{3}-\d{3}-\d{4}", text):
            return True
        return False

    # ---------------- AMOUNTS ----------------

    def _extract_amount_from_block_improved(self, block: List[str], full_text: str) -> Optional[float]:
        def clean_to_float(amt_str: str) -> Optional[float]:
            clean = amt_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
            negative = "-" in amt_str or amt_str.strip().startswith("(")
            try:
                val = float(clean)
                return -val if negative else val
            except:
                return None

        def _is_in_phone_context(s: str, text: str) -> bool:
            digits = s.replace(",", "").replace(".", "")
            return bool(re.search(r"\d{3}[-.\s]\d{3}[-.\s]\d{4}", text)) and digits in text

        all_amounts = []
        for line in block:
            all_amounts.extend(RE_AMOUNT.findall(line))

        floats = [
            (a, clean_to_float(a))
            for a in all_amounts
            if clean_to_float(a) is not None and not _is_in_phone_context(a, full_text)
        ]
        if not floats:
            return None

        dollar_floats = [f for f in floats if "$" in f[0]]
        if dollar_floats:
            return max(dollar_floats, key=lambda x: x[1])[1]
        return max(floats, key=lambda x: x[1])[1]

    # ---------------- DESCRIPTION ----------------

    def _clean_description(self, text: str) -> str:
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        cleaned = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", cleaned)
        cleaned = re.sub(r"\bDAILY ENDING BALANCE\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bFECHA\s+CANTIDAD\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bDATE\s+AMOUNT\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\btrn:\s*", " Trn: ", cleaned, flags=re.I)
        cleaned = re.sub(r"\bssn:\s*", " Ssn: ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    # ---------------- DIRECTION ----------------

    def _determine_direction(
        self, description: str, section_context: str, amount: float, full_text: str
    ) -> str:
        d = description.lower()
        if re.search(r"\b(reversal|reversi[oó]n)\b", d):
            return "in"
        if any(x in d for x in [" fee","charge","cargo","comisión","service charge"]):
            return "out"
        if re.search(r"\b(deposit|credit|incoming|ach credit|wire credit|zelle payment from)\b", d):
            return "in"
        if "card purchase" in d or "compra con tarjeta" in d or "recurring card purchase" in d:
            return "out"
        if "wise us inc" in d or " trnwise " in f" {d} " or re.search(r"\bwise\b", d):
            return "out"
        if any(x in d for x in ["payment to","zelle payment to","online payment",
                                "transferencia a","wire transfer","online domestic wire transfer",
                                "online international wire transfer"]):
            return "out"
        if re.search(r"d[eé]bito de c[aá]mara", d):
            return "out"
        if section_context == "deposits":
            return "in"
        if section_context in ("withdrawals","fees"):
            return "out"
        return "in" if amount > 0 else "out"

