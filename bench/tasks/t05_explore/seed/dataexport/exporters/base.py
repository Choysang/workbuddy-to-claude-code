from ..values import to_text


class Exporter:
    format_name = None

    def __init__(self, columns):
        self.columns = list(columns)

    def text_rows(self, records):
        for record in records:
            yield [to_text(record.get(col)) for col in self.columns]

    def export(self, records):
        raise NotImplementedError
