from docling.document_converter import DocumentConverter

converter = DocumentConverter()

result = converter.convert("sample.pdf")

print(result.document.export_to_markdown())