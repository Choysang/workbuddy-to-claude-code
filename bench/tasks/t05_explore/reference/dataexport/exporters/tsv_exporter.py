from ..registry import register
from ..textutil import escape_control
from .base import Exporter


@register("tsv")
class TsvExporter(Exporter):
    def export(self, records):
        lines = ["\t".join(escape_control(c) for c in self.columns)]
        lines += ["\t".join(escape_control(v) for v in row) for row in self.text_rows(records)]
        return "".join(line + "\n" for line in lines)
