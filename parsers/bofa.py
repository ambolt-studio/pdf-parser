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
    version = "2025.10.03.v8-fix"
    
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
            
            date = self._extract_date(line, year)
            if not date:
                continue
            
            amount = self._extract_amount(line)
            if amount is None:  # ahora no descartamos 0.00 ni montos chicos
                continue
            
            description = self._clean_description(line)
            if not description or len(description) < 5:
                continue
            
            if self._contains_header_phrases(description) or self._looks_like_balance_entry(description):
                continue
            
            direction = self._determine_direction(description, current_section)
            if not direction:
                continue
            
            results.append({
                "date": date,
                "description": description,
                "amount": amount,
                "direction": direction
            })
        
        # --- Deduplicado más fino usando TRN si existe ---
        seen = set()
        unique = []
        for tx in results:
            trn = self._extract_trn(tx["description"]) or ""
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
            has_transaction_indicators = any(indicator in text_lower for indicator in [
                'wire type:', 'online banking', 'zelle', 'transfer', 'payment',
                'checkcard', 'purchase', 'fee', 'deposit', 'withdrawal', 'ach'
            ])
            if not has_transaction_indicators:
                return True
        return False
    
    def _extract_amount(self, line: str) -> float | None:
        amounts = RE_AMOUNT.findall(line)
        if not amounts:
            return None
        amount_str = amounts[-1]
        clean = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        try:
            amount = float(clean)
            # 🔧 quitamos los thresholds que filtraban montos pequeños
            if amount > 100000000:  # solo descartar cosas absurdas
                return None
            return amount
        except:
            return None
    
    def _determine_direction(self, description: str, section_context: str = None) -> str | None:
        desc_lower = description.lower()
        
        if (re.search(r"wire type:\s*wire in", desc_lower) or 
            re.search(r"wire type:\s*intl in", desc_lower) or
            re.search(r"wire type:\s*book in", desc_lower) or
            re.search(r"wire type:\s*fx in", desc_lower) or
            "ach credit" in desc_lower or "ach in" in desc_lower):
            return "in"
        
        if (re.search(r"wire type:\s*wire out", desc_lower) or 
            re.search(r"wire type:\s*intl out", desc_lower) or
            re.search(r"wire type:\s*fx out", desc_lower) or
            re.search(r"wire type:\s*book out", desc_lower) or
            "ach debit" in desc_lower or "ach out" in desc_lower):
            return "out"
        
        if "ccd" in desc_lower:
            return "out" if "debit" in desc_lower else "in"
        
        if "zelle payment from" in desc_lower:
            return "in"
        if "zelle payment to" in desc_lower:
            return "out"
        
        if any(keyword in desc_lower for keyword in ["fee", "charge", "svc charge"]):
            return "out"
        
        if any(keyword in desc_lower for keyword in ["checkcard", "purchase"]):
            return "out"
        
        if any(keyword in desc_lower for keyword in ["deposit", "credit", "received", "cashreward"]):
            return "in"
        
        if section_context == "deposits":
            return "in"
        elif section_context == "withdrawals":
            return "out"
        
        return None
    
    def _extract_trn(self, desc: str) -> str | None:
        m = re.search(r"TRN[:#]?\s*([A-Za-z0-9]+)", desc)
        return m.group(1) if m else None
