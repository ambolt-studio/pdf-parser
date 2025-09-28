    def _determine_direction(self, description: str, section_context: str, amount: float, full_text: str) -> Optional[str]:
        """Determine transaction direction with improved logic for ACH and card transactions"""
        desc_lower = description.lower()
        
        # PRIORITY 1: Specific transaction type patterns (override section context)
        
        # Card purchases and withdrawals are always OUT
        if any(pattern in desc_lower for pattern in [
            "card purchase", "card withdrawal", "compra con tarjeta",
            "recurring card purchase", "lyft", "atlantic broadband", 
            "harvard business serv"
        ]):
            return "out"
        
        # Deposits are always IN
        if "deposit" in desc_lower or "depósito" in desc_lower:
            return "in"
        
        # Payments and transfers OUT
        if any(pattern in desc_lower for pattern in [
            "payment to", "zelle payment to", "online payment",
            "pago a", "transferencia a"
        ]):
            return "out"
        
        # PRIORITY 2: Handle ACH transactions based on section context
        # "orig co name" can be either incoming (credit) or outgoing (debit) depending on section
        if "orig co name" in desc_lower:
            if section_context == "deposits":
                # ACH Credit - incoming transfer (someone sending money to us)
                return "in"
            elif section_context in ["withdrawals", "electronic withdrawals"]:
                # ACH Debit - outgoing transfer (money being taken from us)
                return "out"
            # If no section context, analyze the description
            elif any(indicator in desc_lower for indicator in ["descr:sender", "descr:credit", "credit"]):
                return "in"
            else:
                return "out"
        
        # Other direct debits and electronic payments OUT
        if any(pattern in desc_lower for pattern in [
            "direct debit", "débito directo", "elec pymt", "ach debit"
        ]):
            return "out"
        
        # Fees and charges OUT
        if any(pattern in desc_lower for pattern in [
            "fee", "charge", "cargo", "counter check", "comisión"
        ]):
            return "out"
        
        # PRIORITY 3: Use section context (Chase's structure)
        if section_context == "deposits":
            return "in"
        elif section_context in ["withdrawals", "fees"]:
            return "out"
        
        # PRIORITY 4: Amount sign fallback
        if amount < 0:
            return "out"
        elif amount > 0:
            return "in"
        
        return "out"