import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    RE_AMOUNT,
)

class BOFAParser(BaseBankParser):
    key = "bofa"
    version = "2024.10.04.v1-multi-amount"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        raw_lines = extract_lines(pdf_bytes)
        lines = self._split_concatenated_lines(raw_lines)

        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []

        current_section = None
        in_daily_balances = False

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            # Detectar sección de balances diarios
            if self._is_daily_balance_section(line):
                in_daily_balances = True
                continue

            if in_daily_balances:
                if self._detect_section(line):
                    in_daily_balances = False
                    current_section = self._detect_section(line)
                continue

            section_detected = self._detect_section(line)
            if section_detected:
                current_section = section_detected
                continue

            if self._is_noise_line(line):
                continue

            # Fecha obligatoria
            date = self._extract_date(line, year)
            if not date:
                continue

            # Extraer todos los montos de la línea
            amounts = RE_AMOUNT.findall(line)
            if not amounts:
                continue

            description = self._clean_description(line)
            if not description or len(description) < 5:
                continue

            # Revisar cada monto por separado
            for amt_str in amounts:
                clean = amt_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
                try:
                    amount = float(clean)
                except:
                    continue

                # Filtros de valores extremos
                if amount < 0.01 or amount > 10000000:
                    continue

                desc_lower = description.lower()

                # Ignorar waivers o montos en 0
                if "waiver" in desc_lower or amount == 0:
                    continue

                # Evitar headers o balances disfrazados
                if self._contains_header_phrases(description) or self._looks_like_balance_entry(description):
                    continue

                # Determinar dirección
                direction = self._determine_direction(description, current_section)
                if not direction:
                    continue

                results.append({
                    "date": date,
                    "description": description,
                    "amount": amount,
                    "direction": direction
                })

        # --- Deduplicado controlado ---
        seen = set()
        unique = []
        for tx in results:
            desc_lower = tx["description"].lower()
            trn = self._extract_trn(tx["description"]) or ""

            # Nunca deduplicar Wire Transfer Fee
            if "wire transfer fee" in desc_lower:
                unique.append(tx)
                continue

            key = (tx["date"], tx["amount"], tx["direction"], trn)
            if key not in seen:
                seen.add(key)
                unique.append(tx)

        return unique

    def _looks_like_balance_entry(self, text: str) -> bool:
        text_lower = text.lower()
        dates_without_year = re.findall(r'\b\d{1,2}/\d{1,2}\b(?!/\d{2})', text)
        if len(dates_without_year) >= 2:
            return True
        if re.search(r'\b\d{1,2}/\d{1,2}\b(?!/\d{2})', text):
            has_transaction_indicators = any(ind in text_lower for ind in [
                'wire type:', 'online banking', 'zelle', 'transfer', 'payment',
                'checkcard', 'purchase', 'fee', 'deposit', 'withdrawal'
            ])
            if not has_transaction_indicators:
                return True
        return False

    def _split_concatenated_lines(self, lines: List[str]) -> List[str]:
        """Dividir líneas concatenadas (incluyendo service fees múltiples)"""
        processed = []
        for line in lines:
            if len(line) > 200:
                parts = re.split(r'(\d{1,2}/\d{1,2}/\d{2}\s+)', line)
                temp_line = ""
                for part in parts:
                    if re.match(r'^\d{1,2}/\d{1,2}/\d{2}\s+$', part):
                        if temp_line.strip():
                            processed.append(temp_line.strip())
                        temp_line = part
                    else:
                        temp_line += part
                if temp_line.strip():
                    processed.append(temp_line.strip())
            else:
                processed.append(line)
        return processed

    def _contains_header_phrases(self, text: str) -> bool:
        text_lower = text.lower()
        bad_phrases = [
            "this page intentionally left blank",
            "your checking account",
            "business advantage relationship",
            "business advantage fundamentals",
            "preferred rewards for bus",
            "account summary",
            "important information",
            "daily ledger balances"
        ]
        for phrase in bad_phrases:
            if phrase in text_lower:
                return True
        if re.search(r"account\s*#\s*\d{4}\s+\d{4}\s+\d{4}", text_lower):
            return True
        return False

    def _is_daily_balance_section(self, line: str) -> bool:
        line_lower = line.lower().strip()
        if "daily ledger balances" in line_lower:
            return True
        if re.match(r"^\s*date\s+balance\s*\(\s*\$\s*\)", line_lower):
            return True
        return False

    def _detect_section(self, line: str) -> str | None:
        line_lower = line.lower().strip()
        if "deposits and other additions" in line_lower or "deposits and other credits" in line_lower:
            return "deposits"
        elif "withdrawals and other debits" in line_lower or "other subtractions" in line_lower:
            return "withdrawals"
        elif "atm and debit card subtractions" in line_lower:
            return "withdrawals"
        elif "service fees" in line_lower:
            return "withdrawals"
        return None

    def _is_noise_line(self, line: str) -> bool:
        line_lower = line.lower()
        noise_patterns = [
            "bank of america", "your checking account", "account summary",
            "deposits and other credits", "withdrawals and other debits",
            "service fees", "daily ledger balances", "preferred rewards",
            "important information", "customer service", "page ", " of ",
            "date description amount", "total deposits", "total withdrawals",
            "total service fees", "continued on", "beginning balance",
            "ending balance", "average ledger", "business advantage",
            "this page intentionally"
        ]
        for pattern in noise_patterns:
            if line_lower.strip().startswith(pattern):
                return True
        if re.match(r"^\s*date\s+description\s+amount\s*$", line_lower):
            return True
        if re.match(r"^\s*\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s*$", line):
            return True
        if re.match(r"^\s*\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s+\d{1,2}/\d{1,2}", line):
            return True
        return False

    def _extract_date(self, line: str, year: int) -> str | None:
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})\b", line.strip())
        if match:
            mm, dd, yy = match.groups()
            full_year = int(yy) + 2000 if int(yy) < 50 else int(yy) + 1900
            return f"{full_year:04d}-{int(mm):02d}-{int(dd):02d}"
        return None

    def _clean_description(self, line: str) -> str:
        cleaned = re.sub(r"^\s*\d{1,2}/\d{1,2}/\d{2}\s+", "", line)
        cleaned = re.sub(RE_AMOUNT.pattern, "", cleaned)
        cleaned = re.sub(r"\s*continued\s+on\s+the\s+next\s+page\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _determine_direction(self, description: str, section_context: str = None) -> str | None:
        desc_lower = description.lower()
        if (re.search(r"wire type:\s*wire in", desc_lower) or 
            re.search(r"wire type:\s*intl in", desc_lower) or
            re.search(r"wire type:\s*book in", desc_lower) or
            re.search(r"wire type:\s*fx in", desc_lower)):
            return "in"
        if (re.search(r"wire type:\s*wire out", desc_lower) or 
            re.search(r"wire type:\s*intl out", desc_lower) or
            re.search(r"wire type:\s*fx out", desc_lower) or
            re.search(r"wire type:\s*book out", desc_lower)):
            return "out"
        if "zelle payment from" in desc_lower:
            return "in"
        if "zelle payment to" in desc_lower:
            return "out"
        if "transfer" in desc_lower and "from" in desc_lower and "via wise" in desc_lower:
            return "in"
        if any(keyword in desc_lower for keyword in ["fee", "charge", "svc charge"]):
            return "out"
        if any(keyword in desc_lower for keyword in ["checkcard", "purchase"]):
            return "out"
        if any(keyword in desc_lower for keyword in ["deposit", "credit", "received", "cashreward"]):
            return "in"
        if ("preferred rewards" in desc_lower or "prfd rwds" in desc_lower) and "waiver" in desc_lower:
            return "out"
        if "online banking transfer" in desc_lower or "online transfer" in desc_lower:
            if section_context:
                return "in" if section_context == "deposits" else "out"
        if "ca tlr transfer" in desc_lower:
            if section_context:
                return "in" if section_context == "deposits" else "out"
        if "bkofamerica bc" in desc_lower:
            if section_context:
                return "in" if section_context == "deposits" else "out"
        if section_context == "deposits":
            return "in"
        elif section_context == "withdrawals":
            return "out"
        if "transfer" in desc_lower and "confirmation#" in desc_lower:
            return "out"
        if "online banking" in desc_lower and any(kw in desc_lower for kw in ["payment", "transfer"]):
            return "out"
        if "wise inc" in desc_lower:
            return "out" if "-" in description else "in"
        if "ontop holdings" in desc_lower:
            return "in"
        if "bnf:" in desc_lower:
            return "out"
        return "out"

    def _extract_trn(self, description: str) -> str | None:
        match = re.search(r"\bTRN[:\s]*([A-Za-z0-9]+)", description)
        if match:
            return match.group(1)
        return None
