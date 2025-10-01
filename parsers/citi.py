import re
from typing import List, Dict, Any, Optional
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    RE_AMOUNT,
)

class CitiParser(BaseBankParser):
    key = "citi"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []

        current_section = None
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line or not line.strip():
                i += 1
                continue

            sec = self._detect_section(line)
            if sec:
                current_section = sec
                i += 1
                continue

            if self._is_noise(line):
                i += 1
                continue

            tx_date = self._extract_date(line, year)
            if not tx_date:
                i += 1
                continue

            # build transaction block
            block = [line]
            j = i + 1
            blanks = 0
            while j < len(lines):
                nxt = lines[j]
                if not nxt or not nxt.strip():
                    blanks += 1
                    if blanks >= 2:
                        break
                    j += 1
                    continue
                if self._extract_date(nxt, year):
                    break
                if self._detect_section(nxt):
                    break
                if self._is_noise(nxt):
                    j += 1
                    continue
                block.append(nxt)
                blanks = 0
                j += 1

            tx = self._process_block(block, tx_date, current_section, year)
            if tx:
                results.append(tx)

            i = j

        return results

    # -------------------- Section & noise --------------------

    def _detect_section(self, line: str) -> Optional[str]:
        l = line.lower().strip()
        if "checking activity" in l or "checking account activity" in l or "citibusiness checking activity" in l:
            return "checking"
        if "savings activity" in l:
            return "savings"
        if "citi® savings" in l and "account activity" in l:
            return "savings"
        if "account activity" in l and "amount subtracted" in l and "amount added" in l:
            return "savings"
        return None

    def _is_noise(self, line: str) -> bool:
        l = line.lower().strip()
        noise_prefixes = [
            "citibank", "citibusiness", "relationship summary", "checking summary",
            "customer service information", "page ", "página", "account ", "statement period",
            "service charge summary", "important notice", "important disclosures",
            "fdic insurance", "apy and interest rate", "billing rights summary",
            "in case of errors", "messages from citi", "value of accounts this period",
            "earnings summary this year",
        ]
        for p in noise_prefixes:
            if l.startswith(p):
                return True

        if any(h in l for h in [
            "date description debits credits balance",
            "date description amount subtracted amount added balance",
            "beginning balance", "ending balance", "balance subject", "average daily collected balance",
            "type of charge", "charges debited from account", "total charges for services", "net service charge",
        ]):
            return True

        if re.match(r"^\s*\$[\d,]+\.\d{2}\s*$", line):
            return True
        if re.match(r"^\s*\d{12,}\s*$", line):
            return True

        return False

    # -------------------- Date & block --------------------

    def _extract_date(self, line: str, year: int) -> Optional[str]:
        s = line.strip()
        m = re.match(r"^(\d{1,2})/(\d{1,2})(?:\s|[A-Za-z])", s)
        if not m:
            return None
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            return f"{year:04d}-{mm:02d}-{dd:02d}"
        return None

    def _process_block(
        self,
        block: List[str],
        date: str,
        section_context: Optional[str],
        year: int
    ) -> Optional[Dict[str, Any]]:
        if not block:
            return None
        full = " ".join(x.strip() for x in block if x).strip()
        if not full:
            return None

        if self._contains_legal(full) or self._is_balance_block(full):
            return None

        # special handling for Savings Activity
        if section_context == "savings":
            return self._process_savings_block(block, date, year)

        amount = self._extract_amount(block, full)
        if amount is None:
            return None

        desc = self._clean_description(full)
        if not desc or len(desc) < 3:
            return None

        direction = self._direction_for_citi(desc, section_context or "", amount, full)
        return {
            "date": date,
            "description": desc,
            "amount": amount,
            "direction": direction,
        }

    def _process_savings_block(self, block: List[str], date: str, year: int) -> Optional[Dict[str, Any]]:
        """
        Savings accounts print columns: Date | Description | Amount Subtracted | Amount Added | Balance
        After PDF extraction, 'Amount Subtracted' and 'Amount Added' may appear on same or next line.
        """
        text = " ".join(block)
        # extract both amounts
        tokens = RE_AMOUNT.findall(text)
        if not tokens:
            return None

        # try to isolate two amounts before balance
        floats = []
        for t in tokens:
            clean = t.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
            try:
                val = float(clean)
                floats.append(val)
            except:
                continue

        if not floats:
            return None

        # heuristic: the last value is usually balance, so ignore it
        if len(floats) >= 2:
            possible = floats[:-1]
        else:
            possible = floats

        if not possible:
            return None

        # choose added vs subtracted: smallest non-zero is fee/out, positive is in
        sub_val, add_val = None, None
        if len(possible) == 2:
            sub_val, add_val = possible
        elif len(possible) == 1:
            add_val = possible[0]

        desc = self._clean_description(text)
        if add_val and add_val > 0:
            return {
                "date": date,
                "description": desc,
                "amount": add_val,
                "direction": "in",
            }
        if sub_val and sub_val > 0:
            return {
                "date": date,
                "description": desc,
                "amount": sub_val,
                "direction": "out",
            }
        return None

    def _is_balance_block(self, text: str) -> bool:
        t = text.lower()
        if "daily ending balance" in t:
            return True
        if re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\s+through\s+",
            t
        ):
            if not any(k in t for k in ("deposit", "credit", "debit", "purchase", "withdrawal", "wire", "fee", "interest")):
                return True
        return False

    def _contains_legal(self, text: str) -> bool:
        t = text.lower()
        indicators = [
            "in case of errors", "customer service", "important disclosures",
            "fdic insurance", "apy and interest rate", "billing rights summary",
        ]
        return any(s in t for s in indicators)

    # -------------------- Amount extraction --------------------

    def _extract_amount(self, block: List[str], full_text: str) -> Optional[float]:
        def clean_to_float(amt_str: str) -> Optional[float]:
            neg = False
            if amt_str.strip().startswith("(") and amt_str.strip().endswith(")"):
                neg = True
            if amt_str.strip().startswith("-"):
                neg = True
            clean = amt_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
            try:
                v = float(clean)
                return -v if neg else v
            except:
                return None

        tokens: List[str] = []
        for line in block:
            tokens.extend(RE_AMOUNT.findall(line))

        vals: List[float] = []
        dollar_vals: List[float] = []
        for tok in tokens:
            v = clean_to_float(tok)
            if v is None:
                continue
            vals.append(v)
            if "$" in tok:
                dollar_vals.append(v)

        if not vals:
            return None
        if dollar_vals:
            return max(dollar_vals)
        return max(vals)

    # -------------------- Description cleanup --------------------

    def _clean_description(self, text: str) -> str:
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        cleaned = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", cleaned)
        cleaned = re.sub(r"\bDATE\s+DESCRIPTION\s+.*BALANCE\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bBEGINNING BALANCE\b|\bENDING BALANCE\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    # -------------------- Direction --------------------

    def _direction_for_citi(
        self,
        description: str,
        section_context: str,
        amount: float,
        full_text: str
    ) -> str:
        d = description.lower()
        if any(k in d for k in [
            "electronic credit", "deposit", "interest paid", "interest credit", "wire from"
        ]):
            return "in"
        if "reversal" in d:
            return "in"
        if any(k in d for k in [
            "service charge", "fee for", "incoming wire fee", "monthly maintenance fee"
        ]):
            return "out"
        if any(k in d for k in [
            "debit card purch", "ach debit", "funds trn out", "int'l wire out",
            "international wire out", "cbusol transfer debit", "withdrawal"
        ]):
            return "out"
        if "wire to" in d:
            return "out"
        if "wire from" in d:
            return "in"
        return "in" if amount > 0 else "out"
