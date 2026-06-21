import json
import os
import re
from core.logger import get_logger
from core.models import ExpectedEvent

logger = get_logger(__name__)

# A small set of common English filler words irrelevant for firebase code search
STOPWORDS = {
    "the", "a", "an", "is", "on", "when", "fires", "fire", "once", "and", 
    "to", "of", "in", "that", "this", "with", "user", "successfully", "via", 
    "completes", "navigates", "for", "by", "from", "at", "or", "as", "be", 
    "taps", "button", "page", "screen", "shown", "launched"
}

class SchemaReaderAgent:
    """
    Agent1 SchemaReaderAgent:
    Parses the input schema file (JSON) representing the expected analytics events.
    Extracts relevant keywords and event details per expected event, preparing
    metadata that will be used by subsequent agents (like Agent2 for codebase search).
    """
    def __init__(self, schema_path: str = "schemas/sample_schema.json"):
        self.schema_path = schema_path

    def load_schema(self) -> list[dict]:
        """
        Reads and parses the JSON schema file at schema_path.
        Returns the list of raw event definitions.
        """
        path = self.schema_path
        if not os.path.exists(path):
            # Try to resolve path relative to app root if relative path doesn't exist directly
            possible_paths = [
                os.path.abspath(path),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    path = p
                    break
            else:
                raise FileNotFoundError(f"Schema file not found at: {self.schema_path}")
                
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON from {path}: {e}")
            
        if "events" not in data:
            raise KeyError(f"Missing 'events' key in the schema file at {path}")
            
        return data["events"]

    def _split_identifier(self, text: str) -> list[str]:
        """
        Splits a string on underscores and camelCase/PascalCase boundaries, lowercasing all tokens.
        Example: "add_to_cart" -> ["add", "to", "cart"]
                 "ProductDetailScreen" -> ["product", "detail", "screen"]
        """
        if not text:
            return []
        
        # Replace underscores with spaces
        text = text.replace("_", " ")
        
        # Split camelCase and PascalCase boundaries by injecting spaces
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1 \2', text)
        s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s1)
        
        # Split on whitespace and lowercase
        tokens = s2.split()
        return [t.lower() for t in tokens if t]

    def extract_keywords(self, event: dict) -> list[str]:
        """
        Builds the keyword search list for one event by combining and clean-processing
        the event name, screen identifier, and trigger descriptions.
        """
        event_name = event.get("event_name", "")
        screen = event.get("screen", "")
        trigger_desc = event.get("trigger_description", "")
        
        raw_keywords = []
        
        # 1. Raw event name
        if event_name:
            raw_keywords.append(event_name.lower())
            
        # 2. Raw screen value
        if screen:
            raw_keywords.append(screen.lower())
            
        # 3. Split tokens from event_name and screen
        raw_keywords.extend(self._split_identifier(event_name))
        raw_keywords.extend(self._split_identifier(screen))
        
        # 4. Split tokens from trigger_description, filtered through STOPWORDS
        desc_tokens = re.findall(r'[a-zA-Z0-9]+', trigger_desc)
        for token in desc_tokens:
            t_lower = token.lower()
            if t_lower not in STOPWORDS:
                raw_keywords.append(t_lower)
                
        # Deduplicate preserving first-seen order
        seen = set()
        deduped = []
        for kw in raw_keywords:
            if kw and kw not in seen:
                seen.add(kw)
                deduped.append(kw)
                
        return deduped

    def run(self) -> list[ExpectedEvent]:
        """
        Loads the schema and extracts keywords to build ExpectedEvent models.
        """
        raw_events = self.load_schema()
        logger.info(f"Loaded {len(raw_events)} event(s) from schema.")
        
        expected_events = []
        for event in raw_events:
            keywords = self.extract_keywords(event)
            logger.debug(f"Event '{event.get('event_name')}' keywords: {keywords}")
            
            expected_event = ExpectedEvent(
                event_name=event["event_name"],
                screen=event["screen"],
                expected_params=event.get("expected_params", {}),
                trigger_description=event["trigger_description"],
                keywords=keywords
            )
            expected_events.append(expected_event)
            
        return expected_events

if __name__ == "__main__":
    # Instantiate SchemaReaderAgent with the default sample schema path and execute
    print("Executing SchemaReaderAgent self-test...")
    agent = SchemaReaderAgent()
    try:
        events = agent.run()
        print(f"\nSuccessfully generated {len(events)} ExpectedEvent objects:\n")
        for ev in events:
            print(ev.model_dump_json(indent=2))
            print("-" * 40)
    except Exception as e:
        print(f"Error during SchemaReaderAgent run: {e}")
