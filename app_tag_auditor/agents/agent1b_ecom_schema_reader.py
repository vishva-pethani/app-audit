import os
import json
import core.logger
import agents.agent1_schema_reader
from core.models import ExpectedEcomEvent

class EcomSchemaReaderAgent:
    """
    Loads schemas/ga4_ecom_event_config.json and builds list[ExpectedEcomEvent]
    for all 14 GA4 standard ecommerce events. Reuses Agent 1's _split_identifier for keywords.
    """
    def __init__(self, config_path: str = "schemas/ga4_ecom_event_config.json"):
        self.config_path = config_path
        self._config = None
        self._helper = agents.agent1_schema_reader.SchemaReaderAgent()
        self.logger = core.logger.get_logger(__name__)

    def load_config(self) -> dict:
        if self._config is not None:
            return self._config
        
        path = self.config_path
        if not os.path.exists(path):
            possible_paths = [
                os.path.abspath(path),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
            ]
            path = next((p for p in possible_paths if os.path.exists(p)), path)

        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found at: {self.config_path}")

        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        required_keys = ["events", "event_param_types", "item_param_types", "required_item_params"]
        missing_keys = [k for k in required_keys if k not in config]
        if missing_keys:
            raise ValueError(f"Missing required keys in config: {missing_keys}")

        self._config = config
        return self._config

    def extract_keywords(self, event_name: str, user_action: str,
                        event_param_names: list[str]) -> list[str]:
        raw_keywords = []
        raw_keywords.append(event_name)
        raw_keywords.extend(self._helper._split_identifier(event_name))
        for param in event_param_names:
            raw_keywords.extend(self._helper._split_identifier(param))
        for token in self._helper._split_identifier(user_action):
            if token.lower() not in agents.agent1_schema_reader.STOPWORDS:
                raw_keywords.append(token)

        seen = set()
        deduped = []
        for kw in raw_keywords:
            kw_low = kw.lower()
            if kw_low and kw_low not in seen:
                seen.add(kw_low)
                deduped.append(kw_low)
        return deduped

    def build_event(self, raw_event: dict) -> ExpectedEcomEvent:
        config = self.load_config()
        event_param_names = raw_event["event_params"]
        required_item_param_names = config["required_item_params"]
        min_items = raw_event["min_items"]
        keywords = self.extract_keywords(
            raw_event["event_name"],
            raw_event["user_action"],
            event_param_names
        )
        return ExpectedEcomEvent(
            event_name=raw_event["event_name"],
            user_action=raw_event["user_action"],
            event_param_names=event_param_names,
            required_item_param_names=required_item_param_names,
            min_items=min_items,
            keywords=keywords
        )

    def get_param_type(self, param_name: str, is_item_param: bool) -> str:
        config = self.load_config()
        if is_item_param:
            pool = config["item_param_types"]
        else:
            pool = config["event_param_types"]
        return pool.get(param_name, "string")

    def run(self) -> list[ExpectedEcomEvent]:
        config = self.load_config()
        events = [self.build_event(e) for e in config["events"]]
        self.logger.info(f"Loaded {len(events)} GA4 standard ecommerce events.")
        return events

if __name__ == "__main__":
    agent = EcomSchemaReaderAgent()
    events = agent.run()
    for idx, ev in enumerate(events):
        print(ev.model_dump_json(indent=2))
        if idx < len(events) - 1:
            print("---")
    print("price type (item):", agent.get_param_type("price", True))
    print("transaction_id type (event):", agent.get_param_type("transaction_id", False))
    print("unknown_custom_field type (item):", agent.get_param_type("engine_cc", True))
