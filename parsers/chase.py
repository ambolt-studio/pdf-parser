    def _process_transaction_block(self, block: List[str], date: str, section_context: str, year: int) -> Optional[Dict[str, Any]]:
        """Process a complete transaction block"""
        if not block:
            return None
        
        full_text = " ".join(block)
        
        # Skip if this block contains legal disclaimer content
        if self._contains_legal_content(full_text):
            return None
        
        # Skip if this is a daily ending balance entry
        if self._is_daily_balance_entry(full_text):
            return None
        
        # Extract amount using improved logic
        amount = self._extract_amount_from_block_improved(block, full_text)
        if amount is None or amount == 0:
            return None
        
        # Clean description
        description = self._clean_description(full_text)
        if not description or len(description) < 5:
            return None
        
        # Determine direction with improved logic
        direction = self._determine_direction(description, section_context, amount, full_text)
        if not direction:
            return None
        
        return {
            "date": date,
            "description": description,
            "amount": abs(amount),
            "direction": direction
        }
    
    def _is_daily_balance_entry(self, text: str) -> bool:
        """Check if this transaction block is actually a daily balance entry"""
        text_lower = text.lower()
        
        # Check for daily balance patterns
        balance_patterns = [
            "daily ending balance",
            r"\d+/\d+\s+\$?\d+[\d,]*\.\d{2}\s*$",  # Date followed by amount only
            r"november.*through.*december.*\d+,\s*\d+"  # Date range patterns
        ]
        
        for pattern in balance_patterns:
            if re.search(pattern, text_lower):
                return True
        
        # If text contains date range like "November 30, 2024 through December 31, 2024"
        # and no clear transaction description, it's likely a balance entry
        if re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december).*through.*\d{4}", text_lower):
            # Check if it lacks transaction indicators
            transaction_indicators = ["payment", "transfer", "deposit", "withdrawal", "fee", "charge"]
            if not any(indicator in text_lower for indicator in transaction_indicators):
                return True
        
        return False