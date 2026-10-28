import json

from ..registry import register
from .base import Exporter


@register("jsonl")
class JsonLinesExporter(Exporter):
    def export(self, records):
        lines = [json.dumps(dict(zip(self.columns, row)), ensure_ascii=False) for row in self.text_rows(records)]
        return "".join(line + "\n" for line in lines)
