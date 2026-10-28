from ..registry import register
from ..textutil import escape_control
from .base import Exporter


@register("logfmt")
class LogfmtExporter(Exporter):
    def export(self, records):
        out = []
        for row in self.text_rows(records):
            pairs = []
            for col, value in zip(self.columns, row):
                value = escape_control(value)
                if " " in value or "=" in value or '"' in value:
                    value = '"' + value.replace('"', '\\"') + '"'
                pairs.append(f"{col}={value}")
            out.append(" ".join(pairs) + "\n")
        return "".join(out)
