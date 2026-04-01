import logging


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger com o nome do módulo."""
    return logging.getLogger(name)
