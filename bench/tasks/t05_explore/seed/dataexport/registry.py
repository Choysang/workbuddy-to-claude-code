_REGISTRY = {}


def register(name):
    def decorator(cls):
        if name in _REGISTRY:
            raise ValueError(f"duplicate exporter {name!r}")
        cls.format_name = name
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_exporter(name):
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown format {name!r}") from None


def list_formats():
    return sorted(_REGISTRY)
