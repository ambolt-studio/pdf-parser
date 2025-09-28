    def _clean_description(self, text: str) -> str:
        """Clean description"""
        # Remove amounts
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        
        # Remove dates
        cleaned = re.sub(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*", "", cleaned)
        
        # Remove specific Chase noise that gets mixed with descriptions
        cleaned = re.sub(r"\s*DAILY ENDING BALANCE\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*fecha\s+cantidad\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*date\s+amount\s*", "", cleaned, flags=re.I)
        
        # Remove PDF pagination noise
        cleaned = re.sub(r"\s*\d+\s+\d+\s+November\s+\d+,\s+\d+\s+through\s+\w+\s+\d+,\s+\d+\s*\(continued\)\s*$", "", cleaned, flags=re.I)
        
        # Keep Chase transaction codes but clean up format
        cleaned = re.sub(r"\s*trn:\s*", " Trn: ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*ssn:\s*", " Ssn: ", cleaned, flags=re.I)
        
        # Clean whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        # Capitalize first letter
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
        
        return cleaned