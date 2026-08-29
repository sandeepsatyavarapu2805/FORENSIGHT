from app.ingestion.contracts import ParserAdapter


class ParserRegistry:
    def __init__(self, adapters: list[ParserAdapter] | None = None) -> None:
        self._adapters = adapters or []

    def for_filename(self, filename: str) -> ParserAdapter | None:
        return next(
            (adapter for adapter in self._adapters if adapter.supports_filename(filename)),
            None,
        )


parser_registry = ParserRegistry()


def get_parser_registry() -> ParserRegistry:
    return parser_registry
