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
        if "streamlined checking" in l:
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
            "earnings summary this year", "we are notifying", "effective",
        ]
        for p in noise_prefixes:
            if l.startswith(p):
                return True

        if any(h in l for h in [
            "date description debits credits balance",
            "date description amount subtracted amount added balance",
            "beginning balance:", "ending balance:", "balance subject", "average daily collected balance",
            "type of charge", "charges debited from account", "total charges for services", "net service charge",
            "total debits/credits", "total subtracted/added",
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

        # For checking accounts, extract amount properly
        parsed = self._extract_transaction_amount_and_desc(full)
        if parsed is None:
            return None
        
        amount = parsed["amount"]
        desc = parsed["desc"]

        if not desc or len(desc) < 3:
            return None

        direction = self._direction_for_citi(desc, section_context or "", amount, full)
        return {
            "date": date,
            "description": desc,
            "amount": abs(amount),
            "direction": direction,
        }

    def _process_savings_block(self, block: List[str], date: str, year: int) -> Optional[Dict[str, Any]]:
        """
        Savings accounts print columns: Date | Description | Amount Subtracted | Amount Added | Balance
        We need to extract the correct amounts before the balance.
        """
        text = " ".join(block)
        
        # Extract amounts in order
        parsed = self._extract_savings_amounts(text)
        if not parsed:
            return None

        desc = parsed["desc"]
        amount = parsed["amount"]
        direction = parsed["direction"]

        if not desc or len(desc) < 3:
            return None

        return {
            "date": date,
            "description": desc,
            "amount": amount,
            "direction": direction,
        }

    def _extract_savings_amounts(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract amounts from savings transaction: Amount Subtracted, Amount Added, Balance
        Returns the transaction amount (not balance) and direction.
        """
        matches = list(RE_AMOUNT.finditer(text))
        if not matches:
            return None

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

        # Parse all amounts
        amounts = []
        for match in matches:
            val = clean_to_float(match.group())
            if val is not None:
                amounts.append((val, match.start()))

        if not amounts:
            return None

        # For savings: typically we have 1-3 amounts:
        # - Only Amount Added (or Amount Subtracted) + Balance = 2 amounts
        # - Amount Subtracted + Amount Added + Balance = 3 amounts
        
        # The last amount is usually the balance, so ignore it
        if len(amounts) >= 2:
            transaction_amounts = amounts[:-1]
        else:
            transaction_amounts = amounts

        # Determine which is the transaction amount
        # Look for keywords to determine direction
        text_lower = text.lower()
        
        # Find the transaction amount based on context
        amount = None
        direction = None
        
        if len(transaction_amounts) >= 2:
            # We have both subtracted and added amounts
            sub_amt, add_amt = transaction_amounts[0][0], transaction_amounts[1][0]
            
            # Determine which one is the actual transaction
            if abs(sub_amt) > 0.01 and abs(add_amt) < 0.01:
                amount = abs(sub_amt)
                direction = "out"
            elif abs(add_amt) > 0.01 and abs(sub_amt) < 0.01:
                amount = abs(add_amt)
                direction = "in"
            elif abs(add_amt) > abs(sub_amt):
                amount = abs(add_amt)
                direction = "in"
            else:
                amount = abs(sub_amt)
                direction = "out"
        elif len(transaction_amounts) == 1:
            # Only one transaction amount
            amount = abs(transaction_amounts[0][0])
            
            # Determine direction from keywords
            if any(k in text_lower for k in ["interest", "deposit", "credit", "reversal"]):
                direction = "in"
            elif any(k in text_lower for k in ["fee", "withdrawal", "debit", "withholding"]):
                direction = "out"
            else:
                direction = "in" if transaction_amounts[0][0] > 0 else "out"
        else:
            return None

        # Extract description (remove amounts)
        desc = text
        for match in matches:
            desc = desc.replace(match.group(), " ")
        desc = re.sub(r"\s+", " ", desc).strip()
        
        # Clean up description
        desc = self._clean_description(desc)

        return {
            "amount": amount,
            "direction": direction,
            "desc": desc
        }

    def _extract_transaction_amount_and_desc(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract the transaction amount (not balance) from checking account transactions.
        Format: Date Description Debits Credits Balance
        
        Similar to wf.py's _first_amount_and_cut approach.
        """
        matches = list(RE_AMOUNT.finditer(text))
        if not matches:
            return None

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

        # Parse all amounts
        amounts = []
        for match in matches:
            val = clean_to_float(match.group())
            if val is not None:
                amounts.append((val, match.start()))

        if not amounts:
            return None

        # For checking accounts: Date Description Debits Credits Balance
        # Typically we have 1-2 transaction amounts + 1 balance = 2-3 amounts total
        # The last amount is the balance, which we should ignore
        
        # Strategy: take the first or second amount (not the last which is balance)
        if len(amounts) >= 2:
            # We have at least debits/credits + balance
            # The transaction amount is NOT the last one
            transaction_amounts = amounts[:-1]
            
            # Choose the largest transaction amount (could be debit or credit)
            amount = max(transaction_amounts, key=lambda x: abs(x[0]))[0]
            
            # Cut description before the next amount after our selected amount
            # Find where our amount is in the list
            for i, (val, pos) in enumerate(amounts):
                if val == amount:
                    if i + 1 < len(amounts):
                        cut_at = amounts[i + 1][1]
                        desc = text[:cut_at].rstrip()
                    else:
                        desc = text
                    break
            else:
                desc = text
        else:
            # Only one amount found - use it
            amount = amounts[0][0]
            desc = text

        # Clean description
        desc = self._clean_description(desc)

        return {
            "amount": amount,
            "desc": desc
        }

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
        
        # Incoming transactions
        if any(k in d for k in [
            "electronic credit", "deposit", "interest paid", "interest credit", 
            "wire from", "funds transfer" + "from", "misc deposit"
        ]):
            return "in"
        
        if "reversal" in d:
            return "in"
        
        # Outgoing transactions
        if any(k in d for k in [
            "service charge", "fee for", "incoming wire fee", "monthly maintenance fee",
            "foreign transaction fee", "acct analysis direct db"
        ]):
            return "out"
        
        if any(k in d for k in [
            "debit card purch", "debit card credi", "ach debit", "funds trn out", 
            "int'l wire out", "international wire out", "cbusol transfer debit", 
            "cbusol international wire out", "withdrawal", "instant payment debit",
            "other/withdrawal"
        ]):
            return "out"
        
        if "wire to" in d or "cbusol wire to" in d or "cbol wire to" in d:
            return "out"
        
        # Default: use amount sign
        return "in" if amount > 0 else "out"
