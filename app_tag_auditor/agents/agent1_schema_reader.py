import os
import re
import pandas as pd
from core.logger import get_logger
from core.models import ExpectedEvent, ExpectedParam

logger = get_logger(__name__)

STOPWORDS = {
    "the", "a", "an", "is", "on", "when", "fires", "fire", "once", "and", 
    "to", "of", "in", "that", "this", "with", "user", "successfully", "via", 
    "completes", "navigates", "for", "by", "from", "at", "or", "as", "be", 
    "taps", "button", "page", "screen", "shown", "launched", "clicks", "lands",
    "in", "section"
}

class SchemaReaderAgent:
    """
    Agent1 SchemaReaderAgent:
    Parses real-world schema files (CSV/Excel) representing expected analytics events.
    """
    def __init__(self, schema_path: str = "schemas/sample_schema.csv"):
        self.schema_path = schema_path

    def load_schema(self) -> pd.DataFrame:
        """Reads CSV or Excel schema and validates headers and values."""
        path = self.schema_path
        if not os.path.exists(path):
            possible_paths = [
                os.path.abspath(path),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
            ]
            path = next((p for p in possible_paths if os.path.exists(p)), path)

        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(path)
        elif ext in [".xlsx", ".xls"]:
            df = pd.read_excel(path)
        else:
            raise ValueError(f"Unsupported format '{ext}'. Use .csv, .xlsx, or .xls.")

        df.columns = [col.strip() for col in df.columns]
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
        df = df.fillna("")

        expected_cols = [
            "User Action", "Screen Name", "Event Name", "Event Parameters",
            "Parameter Type", "Data Type", "Principle", "Event Parameters Example Values"
        ]
        missing = [col for col in expected_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Missing expected columns: {missing}")

        return df

    def _split_identifier(self, text: str) -> list[str]:
        """Splits on underscores/spaces first, then on camelCase boundaries."""
        if not text:
            return []
        tokens = []
        for part in re.split(r'[_ ]+', text):
            if part:
                s1 = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', part)
                s2 = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', s1)
                tokens.extend([t.lower() for t in s2.split()])
        return tokens

    def _parse_params_list(self, raw: str) -> list[str]:
        """Splits parameter cells on commas and strips whitespace."""
        return [x.strip() for x in raw.split(",") if x.strip()] if raw else []

    def _parse_principle(self, raw_principle: str, param_names: list[str]) -> dict[str, str] | None:
        """Attempts to parse principle cell per parameter. Returns None if unparseable."""
        if not raw_principle or not param_names:
            return None
        parsed = {}
        for seg in raw_principle.split(";"):
            if not seg.strip():
                continue
            if "=" not in seg:
                return None
            k, v = seg.split("=", 1)
            k = k.strip().lower()
            match = next((p for p in param_names if p.lower() == k), None)
            if not match:
                return None
            parsed[match] = v.strip()
        return parsed if len(parsed) == len(param_names) else None

    def _parse_example_values(self, raw: str) -> dict[str, str]:
        """Parses key-value examples formatted as key=value."""
        if not raw:
            return {}
        result = {}
        for piece in raw.split(","):
            if "=" in piece:
                k, v = piece.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def _broadcast(self, raw: str, count: int) -> list[str]:
        """Broadcasts single parameter values to match the target parameter count."""
        items = [x.strip() for x in raw.split(",")] if raw else []
        if len(items) == count:
            return items
        if len(items) == 1:
            return items * count
        logger.warning(f"Broadcast mismatch. Expected {count}, got {len(items)}. Padding/truncating.")
        if not items:
            return [""] * count
        return (items + [items[-1]] * count)[:count]

    def extract_keywords(self, event_name: str, screen: str, user_action: str, param_names: list[str]) -> list[str]:
        """Combines details from identifiers and triggers into search keywords."""
        raw_keywords = []
        if event_name:
            raw_keywords.append(event_name.lower())
        if screen:
            raw_keywords.append(screen.lower())
            
        raw_keywords.extend(self._split_identifier(event_name))
        raw_keywords.extend(self._split_identifier(screen))
        
        for p in param_names:
            raw_keywords.extend(self._split_identifier(p))

        action_tokens = re.findall(r'[a-zA-Z0-9]+', user_action)
        raw_keywords.extend([t.lower() for t in action_tokens if t.lower() not in STOPWORDS])

        seen = set()
        deduped = []
        for kw in raw_keywords:
            if kw and kw not in seen:
                seen.add(kw)
                deduped.append(kw)
        return deduped

    def build_event(self, row: dict) -> ExpectedEvent:
        """Processes a single row from the schema into an ExpectedEvent model."""
        event_name = row.get("Event Name", "")
        screen = row.get("Screen Name", "")
        user_action = row.get("User Action", "")
        raw_params = row.get("Event Parameters", "")
        raw_param_type = row.get("Parameter Type", "")
        raw_data_type = row.get("Data Type", "")
        raw_principle = row.get("Principle", "")
        raw_examples = row.get("Event Parameters Example Values", "")

        param_names = self._parse_params_list(raw_params)
        count = len(param_names)

        param_types = self._broadcast(raw_param_type, count)
        data_types = self._broadcast(raw_data_type, count)
        parsed_principles = self._parse_principle(raw_principle, param_names)
        parsed_examples = self._parse_example_values(raw_examples)

        expected_params = []
        for idx, name in enumerate(param_names):
            principle = parsed_principles[name] if parsed_principles and name in parsed_principles else raw_principle
            example_val = parsed_examples.get(name, "")
            
            expected_params.append(ExpectedParam(
                param_name=name,
                parameter_type=param_types[idx],
                data_type=data_types[idx],
                principle=principle,
                example_value=example_val
            ))

        keywords = self.extract_keywords(event_name, screen, user_action, param_names)
        return ExpectedEvent(
            event_name=event_name,
            screen=screen,
            user_action=user_action,
            expected_params=expected_params,
            raw_principle=raw_principle,
            keywords=keywords
        )

    def run(self) -> list[ExpectedEvent]:
        """Loads and processes all events in the schema."""
        df = self.load_schema()
        logger.info(f"Loaded {len(df)} rows from schema.")
        
        events = []
        for _, row in df.iterrows():
            events.append(self.build_event(row.to_dict()))
        return events

if __name__ == "__main__":
    print("Executing SchemaReaderAgent self-test with new real-world layout...")
    agent = SchemaReaderAgent()
    try:
        events = agent.run()
        print(f"\nSuccessfully generated {len(events)} ExpectedEvent objects:\n")
        for ev in events:
            print(ev.model_dump_json(indent=2))
            print("-" * 40)
    except Exception as e:
        print(f"Error during SchemaReaderAgent run: {e}")
        import traceback
        traceback.print_exc()
