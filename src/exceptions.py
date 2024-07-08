class ParserFindTagException(Exception):
    """Вызывается, когда парсер не может найти тег."""
    pass


class NotFoundException(Exception):
    """Исключение, выбрасываемое, когда элемент не найден."""
    pass
