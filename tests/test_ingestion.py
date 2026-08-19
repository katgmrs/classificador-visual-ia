from io import BytesIO
import unittest

import pandas as pd

from src.portfolio.ingestion import SpreadsheetValidationError, read_spreadsheet


def workbook_bytes(rows):
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return buffer.getvalue()


class IngestionTests(unittest.TestCase):
    def test_reads_expected_columns_and_counts_reused_media(self):
        content = workbook_bytes([
            {"Vídeo": "A", "ID": "one", "JWPlayer ID": "Ab12Cd34", "Palavras-chave": "x"},
            {"Vídeo": "B", "ID": "two", "JWPlayer ID": "Ab12Cd34", "Palavras-chave": "y"},
        ])
        rows, report = read_spreadsheet(content, "base.xlsx")
        self.assertEqual(len(rows), 2)
        self.assertEqual(report, {"rows": 2, "unique_media": 1, "reused_media": 1})

    def test_rejects_invalid_jwplayer_id(self):
        content = workbook_bytes([{"Vídeo": "A", "ID": "one", "JWPlayer ID": "inválido"}])
        with self.assertRaisesRegex(SpreadsheetValidationError, "JWPlayer ID inválido"):
            read_spreadsheet(content, "base.xlsx")


if __name__ == "__main__":
    unittest.main()
