import csv
import io

from ..registry import register
from .base import Exporter


@register("csv")
class CsvExporter(Exporter):
    def export(self, records):
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(self.columns)
        writer.writerows(self.text_rows(records))
        return buf.getvalue()
