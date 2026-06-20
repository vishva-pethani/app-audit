import logging
import os

def get_logger(name: str) -> logging.Logger:
    """
    Creates and returns a consistent logger configured with console and file output handlers.
    Automatically creates the logs/ directory if it does not exist.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Formatter: timestamp - level - name - message
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File handler
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(log_dir, "app_tag_auditor.log"))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger
