"""
Kannada Messages Service - Generate traffic messages in Kannada and English
Based on actual traffic status and conditions
"""

from typing import Dict, Optional

class KannadaMessagesService:
    """
    Service for generating bilingual traffic messages (English + Kannada)
    """
    
    # Message templates based on traffic status
    MESSAGES = {
        "LOW": {
            "english": "Traffic is flowing freely. No significant delays expected.",
            "kannada": "ಟ್ರಾಫಿಕ್ ಸುಲಭವಾಗಿ ಹರಿಯುತ್ತಿದೆ. ಗಣನೀಯ ವಿಳಂಬಗಳನ್ನು ನಿರೀಕ್ಷಿಸಲಾಗಿಲ್ಲ."
        },
        "MODERATE": {
            "english": "Moderate traffic. Slight delays possible.",
            "kannada": "ಮಧ್ಯಮ ಟ್ರಾಫಿಕ್. ಸ್ವಲ್ಪ ವಿಳಂಬಗಳು ಸಾಧ್ಯ."
        },
        "HIGH": {
            "english": "Heavy traffic. Expect delays. Consider alternative routes if available.",
            "kannada": "ಭಾರಿ ಟ್ರಾಫಿಕ್. ವಿಳಂಬಗಳನ್ನು ನಿರೀಕ್ಷಿಸಿ. ಲಭ್ಯವಿದ್ದರೆ ಪರ್ಯಾಯ ಮಾರ್ಗಗಳನ್ನು ಪರಿಗಣಿಸಿ."
        },
        "SEVERE": {
            "english": "Severe congestion. Significant delays. Use alternative routes if possible.",
            "kannada": "ತೀವ್ರ ಸಂದಣಿ. ಗಣನೀಯ ವಿಳಂಬಗಳು. ಸಾಧ್ಯವಾದರೆ ಪರ್ಯಾಯ ಮಾರ್ಗಗಳನ್ನು ಬಳಸಿ."
        },
        "UNKNOWN": {
            "english": "Traffic status unknown. Using routing provider estimate.",
            "kannada": "ಟ್ರಾಫಿಕ್ ಸ್ಥಿತಿ ತಿಳಿದಿಲ್ಲ. ರೂಟಿಂಗ್ ಪ್ರೊವೈಡರ್ ಅಂದಾಜನ್ನು ಬಳಸಲಾಗುತ್ತಿದೆ."
        },
        "INCIDENT": {
            "english": "Incident detected on route. Expect delays.",
            "kannada": "ಮಾರ್ಗದಲ್ಲಿ ಘಟನೆ ಪತ್ತೆಹಚ್ಚಲಾಗಿದೆ. ವಿಳಂಬಗಳನ್ನು ನಿರೀಕ್ಷಿಸಿ."
        },
        "REROUTE_RECOMMENDED": {
            "english": "Alternative route recommended due to better conditions.",
            "kannada": "ಉತ್ತಮ ಸ್ಥಿತಿಗಳಿಂದಾಗಿ ಪರ್ಯಾಯ ಮಾರ್ಗವನ್ನು ಶಿಫಾರಸು ಮಾಡಲಾಗಿದೆ."
        },
        "WEATHER_IMPACT": {
            "english": "Weather conditions may affect traffic. Drive carefully.",
            "kannada": "ಹವಾಮಾನ ಸ್ಥಿತಿಗಳು ಟ್ರಾಫಿಕ್ ಅನ್ನು ಪ್ರಭಾವಿಸಬಹುದು. ಎಚ್ಚರಿಕೆಯಿಂದ ಚಾಲನೆ ಮಾಡಿ."
        }
    }
    
    def generate_message(self, traffic_status: str, has_incident: bool = False, 
                         weather_impact: bool = False, reroute_recommended: bool = False) -> Dict:
        """
        Generate bilingual message based on traffic conditions
        
        Args:
            traffic_status: Traffic status (LOW, MODERATE, HIGH, SEVERE)
            has_incident: Whether there's an incident on the route
            weather_impact: Whether weather is affecting traffic
            reroute_recommended: Whether rerouting is recommended
            
        Returns:
            Dictionary with English and Kannada messages
        """
        english_parts = []
        kannada_parts = []
        
        # Start with traffic status message
        if traffic_status in self.MESSAGES:
            english_parts.append(self.MESSAGES[traffic_status]["english"])
            kannada_parts.append(self.MESSAGES[traffic_status]["kannada"])
        
        # Add incident message if applicable
        if has_incident:
            english_parts.append(self.MESSAGES["INCIDENT"]["english"])
            kannada_parts.append(self.MESSAGES["INCIDENT"]["kannada"])
        
        # Add weather impact message if applicable
        if weather_impact:
            english_parts.append(self.MESSAGES["WEATHER_IMPACT"]["english"])
            kannada_parts.append(self.MESSAGES["WEATHER_IMPACT"]["kannada"])
        
        # Add reroute recommendation if applicable
        if reroute_recommended:
            english_parts.append(self.MESSAGES["REROUTE_RECOMMENDED"]["english"])
            kannada_parts.append(self.MESSAGES["REROUTE_RECOMMENDED"]["kannada"])
        
        # Combine messages - use UNKNOWN status if no status provided
        if not english_parts and not kannada_parts:
            if traffic_status in self.MESSAGES:
                return self.get_simple_message(traffic_status)
            else:
                return self.get_simple_message("UNKNOWN")
        
        english_message = " ".join(english_parts) if english_parts else "Traffic information unavailable."
        kannada_message = " ".join(kannada_parts) if kannada_parts else "ಟ್ರಾಫಿಕ್ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ."
        
        return {
            "english": english_message,
            "kannada": kannada_message,
            "traffic_status": traffic_status,
            "has_incident": has_incident,
            "weather_impact": weather_impact,
            "reroute_recommended": reroute_recommended
        }
    
    # State-specific incident messages for the unexpected-traffic detector
    # (traffic_incident_service.py) -- kept separate from MESSAGES above
    # (which are keyed by the older LOW/MODERATE/HIGH/SEVERE route-level
    # vocabulary) because the incident detector's states are a different,
    # more precise vocabulary that must never be blurred together: never
    # say "accident" unless PROVIDER_CONFIRMED_INCIDENT, never call a
    # possible blockage a confirmed one.
    INCIDENT_MESSAGES = {
        "TRAFFIC_ANOMALY": {
            "english": "Unexpected heavy traffic detected on {road}. Please consider an alternate route.",
            "kannada": "{road} ನಲ್ಲಿ ನಿರೀಕ್ಷೆಗಿಂತ ಹೆಚ್ಚು ಸಂಚಾರ ದಟ್ಟಣೆ ಪತ್ತೆಯಾಗಿದೆ. ಪರ್ಯಾಯ ಮಾರ್ಗವನ್ನು ಪರಿಗಣಿಸಿ.",
        },
        "POSSIBLE_TRAFFIC_BLOCKAGE": {
            "english": "Possible traffic blockage detected on {road}. Please consider an alternate route.",
            "kannada": "{road} ನಲ್ಲಿ ಸಂಭವನೀಯ ಸಂಚಾರ ತಡೆ ಪತ್ತೆಯಾಗಿದೆ. ದಯವಿಟ್ಟು ಪರ್ಯಾಯ ಮಾರ್ಗವನ್ನು ಪರಿಗಣಿಸಿ.",
        },
        "PROVIDER_CONFIRMED_INCIDENT": {
            "english": "Confirmed traffic incident on {road}. Please consider an alternate route.",
            "kannada": "{road} ನಲ್ಲಿ ದೃಢಪಡಿಸಿದ ಸಂಚಾರ ಘಟನೆ ಪತ್ತೆಯಾಗಿದೆ. ದಯವಿಟ್ಟು ಪರ್ಯಾಯ ಮಾರ್ಗವನ್ನು ಪರಿಗಣಿಸಿ.",
        },
    }

    def generate_incident_alert(self, incident_type: str, road_name: Optional[str]) -> Optional[Dict]:
        """Bilingual (English + Kannada) alert text for one detected
        unexpected-traffic incident -- state-specific wording only, never
        a generic 'incident'/'accident' string, and never fabricated for
        NORMAL_CONGESTION/HEAVY_CONGESTION (returns None for those,
        matching traffic_incident_service.user_alert_message's own rule
        that only TRAFFIC_ANOMALY and above ever produce a user message)."""
        template = self.INCIDENT_MESSAGES.get(incident_type)
        if not template:
            return None
        road = road_name or "this road"
        return {
            "english": template["english"].format(road=road),
            "kannada": template["kannada"].format(road=road),
            "incident_type": incident_type,
            "road_name": road_name,
        }

    def get_simple_message(self, status: str) -> Dict:
        """
        Get a simple message for a given status
        
        Args:
            status: Traffic status
            
        Returns:
            Dictionary with English and Kannada messages
        """
        if status in self.MESSAGES:
            return {
                "english": self.MESSAGES[status]["english"],
                "kannada": self.MESSAGES[status]["kannada"]
            }
        else:
            return {
                "english": "Traffic status unknown.",
                "kannada": "ಟ್ರಾಫಿಕ್ ಸ್ಥಿತಿ ತಿಳಿದಿಲ್ಲ."
            }


# Singleton instance
_kannada_service = None

def get_kannada_service() -> KannadaMessagesService:
    """Get or create the Kannada messages service singleton"""
    global _kannada_service
    if _kannada_service is None:
        _kannada_service = KannadaMessagesService()
    return _kannada_service
