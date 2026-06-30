import os
import sys
import json
import re

# Add the project root to sys.path to allow execution from any directory
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.logger import get_logger
from core.models import ExpectedEcomEvent
import agents.agent1_schema_reader
from agents.agent1_schema_reader import STOPWORDS

logger = get_logger(__name__)

class EcomSchemaReaderAgent:
    def __init__(self, config_path: str = "schemas/ga4_ecom_event_config.json"):
        self.config_path = config_path
        self._config = None
        self._helper = agents.agent1_schema_reader.SchemaReaderAgent()

    def load_config(self) -> dict:
        path = self.config_path
        if not os.path.exists(path):
            possible_paths = [
                os.path.abspath(path),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
            ]
            path = next((p for p in possible_paths if os.path.exists(p)), path)

        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse config JSON: {e}")

        required_keys = ["events", "event_param_types", "item_param_types", "required_item_params"]
        missing_keys = [k for k in required_keys if k not in config]
        if missing_keys:
            raise ValueError(f"Missing required configuration keys: {missing_keys}")

        self._config = config
        return config

    def extract_keywords(self, event_name: str, user_action: str, event_param_names: list[str]) -> list[str]:
        raw_keywords = []
        if event_name:
            raw_keywords.append(event_name.lower())

        raw_keywords.extend(self._helper._split_identifier(event_name))

        for param in event_param_names:
            raw_keywords.extend(self._helper._split_identifier(param))

        action_tokens = re.findall(r'[a-zA-Z0-9]+', user_action)
        raw_keywords.extend([t.lower() for t in action_tokens if t.lower() not in STOPWORDS])

        seen = set()
        deduped = []
        for kw in raw_keywords:
            if kw:
                kw_lower = kw.lower()
                if kw_lower not in seen:
                    seen.add(kw_lower)
                    deduped.append(kw_lower)
        return deduped

    def build_event(self, raw_event: dict) -> ExpectedEcomEvent:
        if self._config is None:
            self.load_config()
        required_item_param_names = self._config["required_item_params"]
        event_param_names = raw_event["event_params"]
        min_items = raw_event["min_items"]
        keywords = self.extract_keywords(raw_event["event_name"], raw_event["user_action"], event_param_names)
        return ExpectedEcomEvent(
            event_name=raw_event["event_name"],
            user_action=raw_event["user_action"],
            event_param_names=event_param_names,
            required_item_param_names=required_item_param_names,
            min_items=min_items,
            keywords=keywords
        )

    def run(self) -> list[ExpectedEcomEvent]:
        if self._config is None:
            self.load_config()
        events = [self.build_event(e) for e in self._config["events"]]
        logger.info(f"Loaded {len(events)} GA4 standard ecommerce events.")
        return events

    def get_param_type(self, param_name: str, is_item_param: bool) -> str:
        if self._config is None:
            self.load_config()
        if is_item_param:
            return self._config["item_param_types"].get(param_name, "string")
        else:
            return self._config["event_param_types"].get(param_name, "string")

if __name__ == "__main__":
    reader = EcomSchemaReaderAgent()
    try:
        events = reader.run()
        print(f"Loaded {len(events)} ExpectedEcomEvents:")
        for ev in events:
            print(ev.model_dump_json(indent=2))
        
        print("\nSanity Check:")
        print("Price type:", reader.get_param_type("price", True))
        print("Transaction ID type:", reader.get_param_type("transaction_id", False))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
