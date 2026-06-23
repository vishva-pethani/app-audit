import xml.etree.ElementTree as ET
from core.logger import get_logger

logger = get_logger(__name__)

def dump_hierarchy(driver) -> str:
    """
    Dumps the current screen hierarchy. Wraps in try/except and returns empty string on failure.
    """
    if driver is None:
        return ""
    try:
        return driver.page_source
    except Exception as e:
        logger.error(f"Failed to dump hierarchy: {e}")
        return ""

def parse_hierarchy(xml_str: str) -> ET.Element | None:
    """
    Parses the hierarchy XML string. Returns the root element or None if invalid.
    """
    if not xml_str or not xml_str.strip():
        return None
    try:
        return ET.fromstring(xml_str.encode('utf-8'))
    except ET.ParseError as e:
        logger.error(f"Failed to parse hierarchy XML: {e}")
        return None
