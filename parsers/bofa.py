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
        
        for line in lines:
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
            if amount is None:
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
        
        # Deduplicado por TRN
        seen = set()
        unique = []
        for tx in results:
            trn = self._extract_trn(tx["description"]) or ""
            key = (tx["date"], tx["amount"], tx["direction"], trn)
            if key not in seen:
                seen.add(key)
                unique.append(tx)
        
        return unique

    # --- Helpers del original (mantener todos) ---

    def _split_concatenated_lines(self, lines: List[str]) -> List[str]:
        # … el mismo que ya tenías en tu versión original …
        ...

    def _contains_header_phrases(self, text: str) -> bool:
        ...
    
    def _is_daily_balance_section(self, line: str) -> bool:
        ...
    
    def _detect_section(self, line: str) -> str | None:
        ...
    
    def _is_noise_line(self, line: str) -> bool:
        ...
    
    def _extract_date(self, line: str, year: int) -> str | None:
        ...
    
    def _clean_description(self, line: str) -> str:
        ...

    def _looks_like_balance_entry(self, text: str) -> bool:
        # igual que antes pero con "ach" añadido a indicadores
        ...

    def _extract_amount(self, line: str) -> float | None:
        # versión modificada (solo límite alto, no descarta montos pequeños)
        ...

    def _determine_direction(self, description: str, section_context: str = None) -> str | None:
        # versión extendida con ACH/CCD
        ...

    def _extract_trn(self, desc: str) -> str | None:
        m = re.search(r"TRN[:#]?\s*([A-Za-z0-9]+)", desc)
        return m.group(1) if m else None

