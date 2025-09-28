    def _detect_section(self, line: str) -> Optional[str]:
        """Detect which section of the statement we're in"""
        line_lower = line.lower().strip()
        
        # Standard Chase sections (Spanish/English)
        if any(pattern in line_lower for pattern in [
            "depósitos y adiciones", "deposits and additions"
        ]):
            return "deposits"
        
        if any(pattern in line_lower for pattern in [
            "retiros electrónicos", "electronic withdrawals"
        ]):
            return "withdrawals"
        
        if line_lower == "cargos" or line_lower == "charges" or line_lower == "fees":
            return "fees"
        
        # ATM and Debit Card sections (these are withdrawals)
        if any(pattern in line_lower for pattern in [
            "atm & debit card withdrawals", 
            "atm and debit card withdrawals",
            "card purchases"
        ]):
            return "withdrawals"
        
        return None