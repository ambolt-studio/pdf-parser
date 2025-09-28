    def _is_basic_noise(self, line: str) -> bool:
        """Basic noise filtering - only obvious non-transactions"""
        line_lower = line.lower().strip()
        
        # PDF markup
        if "*start*" in line_lower or "*end*" in line_lower:
            return True
        
        # Obvious headers
        basic_noise = [
            "jpmorgan chase bank",
            "página", "page",
            "número de cuenta", "account number",
            "total de depósitos", "total deposits",
            "total de retiros", "total withdrawals", 
            "total comisiones", "total fees",
            "saldo inicial", "beginning balance",
            "saldo final", "ending balance",
            "duplicate statement",
            "customer service information",
            "checking summary",
            "how to avoid the monthly service fee",
            "daily ending balance",
            "resumen de cuenta",
            "rendimiento porcentual anual",
            "cantidad"  # Changed from full phrase to catch variations
        ]
        
        for pattern in basic_noise:
            if line_lower.startswith(pattern):
                return True
        
        # Just amounts (balances) - but not transaction lines with amounts
        if re.match(r"^\s*\$[\d,]+\.\d{2}\s*$", line):
            return True
            
        # Account numbers only
        if re.match(r"^\s*\d{12,}\s*$", line):
            return True
        
        # Very specific legal disclaimer start
        if line_lower.startswith("en caso de errores o preguntas sobre sus transferencias electrónicas"):
            return True
        if line_lower.startswith("in case of errors or questions about your electronic funds transfers"):
            return True
        
        return False