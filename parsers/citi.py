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

class CitiParser(BaseBankParser):
    key = "citi"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []

        current_section = None  # "checking" | "savings" | None
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line or not line.strip():
                i += 1
                continue

            # Detect high-level section
            sec = self._detect_section(line)
            if sec:
                current_section = sec
                i += 1
                continue

            # Skip obvious noise and summaries
            if self._is_noise(line):
                i += 1
                continue

            # Transaction lines start with MM/DD (Citi)
            tx_date = self._extract_date(line, year)
            if not tx_date:
                i += 1
                continue

            # Collect a transaction block (line + following detail lines until next date/section)
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
                if self._detect_section(nxt) is not None:
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
        # Checking
        if "checking activity" in l or "citibusiness streamlined checking" in l:
            return "checking"
        # Savings / personal "Account Activity"
        if "savings" in l and "account activity" in l:
            return "savings"
        if "account activity" in l and "savings" in l:
            return "savings"
        # Some personal statements show only "Account Activity" under "Citi Savings"
        if "citi® savings" in l and ("account activity" in l or "account activity" in l):
            return "savings"
        return None

    def _is_noise(self, line: str) -> bool:
        l = line.lower().strip()

        # Obvious headers, page info, addresses, etc.
        noise_prefixes = [
            "citibank", "citibusiness", "relationship summary", "checking summary",
            "customer service information", "page ", "página", "account ", "statement period",
            "service charge summary", "important notice", "important disclosures",
            "amendments to the citibusiness client manual", "fdic insurance",
            "apy and interest rate", "billing rights summary", "in case of errors",
            "messages from citi", "citi priority", "value of accounts this period",
            "earnings summary this year",
        ]
        for p in noise_prefixes:
            if l.startswith(p):
                return True

        # Column headers and balance lines
        if any(h in l for h in [
            "date description debits credits balance",
            "date description amount subtracted amount added balance",
            "beginning balance", "ending balance", "balance subject", "average daily collected balance",
            "type of charge", "charges debited from account", "total charges for services", "net service charge",
        ]):
            return True

        # Raw numbers or balances only
        if re.match(r"^\s*\$[\d,]+\.\d{2}\s*$", line):
            return True
        if re.match(r"^\s*\d{12,}\s*$", line):
            return True

        return False

    # -------------------- Date & block --------------------

    def _extract_date(self, line: str, year: int) -> Optional[str]:
        s = line.strip()
        # Citi puts MM/DD at the start of transaction rows
        m = re.match(r"^(\d{1,2})/(\d{1,2})(?:\s|$)", s)
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

    def _is_balance_block(self, text: str) -> bool:
        t = text.lower()
        if "daily ending balance" in t:
            return True
        # lines that only describe date range headers and no txn words
        if re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\s+through\s+",
            t
        ):
            if not any(k in t for k in ("deposit", "credit", "debit", "purchase", "withdrawal", "wire", "fee", "interest")):
                return True
        return False

    def _contains_legal(self, text: str) -> bool:
        t = text.lower()
        # typical disclaimers and legal paragraphs
        indicators = [
            "in case of errors", "customer service", "important disclosures",
            "fdic insurance", "apy and interest rate", "billing rights summary",
        ]
        return any(s in t for s in indicators)

    # -------------------- Amount extraction --------------------

    def _extract_amount(self, block: List[str], full_text: str) -> Optional[float]:
        """
        Citi: amounts are in columns; in raw text they end up as numbers at end of row or within the block.
        Rules:
          - Prioritize values with '$'
          - Filter out phones (###-###-####), ZIP+4 (#####-####), "Card 1234"
          - Choose the highest valid value (main txn amount). Handle parentheses and minus.
        """
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

        def in_phone_context(s: str, text: str) -> bool:
            digits = s.replace(",", "").replace(".", "")
            # phone pattern anywhere, and this number appears within it
            return bool(re.search(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", text)) and digits in text

        def in_zip4_context(s: str, text: str) -> bool:
            # ZIP+4: 33132-1234, avoid grabbing fragments
            if not re.search(r"\b\d{5}-\d{4}\b", text):
                return False
            dig = s.replace(",", "").replace(".", "")
            return dig in text

        def in_card_suffix(s: str, text: str) -> bool:
            # "Card 1197" / "Card Ending in 8867"
            core = s.replace(",", "").split(".")[0]
            return bool(re.search(rf"\bCard(\s+Ending\s+in)?\s+{re.escape(core)}\b", text, re.I))

        # gather all money-like tokens using repo's RE_AMOUNT
        tokens: List[str] = []
        for line in block:
            tokens.extend(RE_AMOUNT.findall(line))

        # normalize to floats and filter invalid contexts
        vals: List[float] = []
        dollar_vals: List[float] = []
        for tok in tokens:
            if in_phone_context(tok, full_text) or in_zip4_context(tok, full_text) or in_card_suffix(tok, full_text):
                continue
            v = clean_to_float(tok)
            if v is None:
                continue
            vals.append(v)
            if "$" in tok:
                dollar_vals.append(v)

        if not vals:
            return None

        # Prefer $ amounts; otherwise take the highest (Citi rows often repeat small fees alongside main amounts)
        if dollar_vals:
            return max(dollar_vals)
        return max(vals)

    # -------------------- Description cleanup --------------------

    def _clean_description(self, text: str) -> str:
        # remove amounts
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        # remove MM/DD tokens
        cleaned = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", cleaned)
        # remove frequent headers/residual column names
        cleaned = re.sub(r"\bDATE\s+DESCRIPTION\s+DEBITS\s+CREDITS\s+BALANCE\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bDATE\s+DESCRIPTION\s+AMOUNT\s+SUBTRACTED\s+AMOUNT\s+ADDED\s+BALANCE\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bBEGINNING BALANCE\b|\bENDING BALANCE\b", "", cleaned, flags=re.I)

        # compact whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # capitalize first letter
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

        # Credits (in)
        if any(k in d for k in [
            "electronic credit", "deposit", "interest paid", "interest credit",
            "wire from", "funds transfer"  # but be careful: "FUNDS TRN OUT" is out (see below)
        ]):
            # disambiguate "funds transfer" generic: look for "from" vs "out"
            if "funds trn out" in d or "cbusol transfer debit" in d or "international wire out" in d or "int'l wire out" in d:
                pass
            else:
                # also accept explicit "from" on wire lines
                if "wire from" in d or "from" in d:
                    return "in"
                # generic ELECTRONIC CREDIT/DEPOSIT/INTEREST
                if "electronic credit" in d or "deposit" in d or "interest" in d:
                    return "in"

        # Reversals are IN (e.g., Federal Withholding Tax Reversal)
        if "reversal" in d:
            return "in"

        # Fees & charges: OUT
        if any(k in d for k in [
            "service charge", "service charges", "fee for", "incoming wire fee",
            "monthly maintenance fee"
        ]):
            return "out"

        # Clear debits: OUT
        if any(k in d for k in [
            "debit card purch", "ach debit", "funds trn out", "int'l wire out",
            "intl wire out", "international wire out", "cbusol transfer debit",
            "other/withdrawal/adj", "other/withdrawal", "withdrawal"
        ]):
            return "out"

        # Generic wire transfer lines:
        if "wire to" in d:
            return "out"
        if "wire from" in d:
            return "in"

        # Section fallback (checking/savings doesn't strictly imply in/out, so we avoid it)
        # Final fallback by sign (rarely used since Citi prints positive numbers; logic above should classify)
        return "in" if amount > 0 else "out"
