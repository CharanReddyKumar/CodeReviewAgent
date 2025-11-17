"""Tests for best_practices_docs.py - Complete coverage"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from best_practices_docs import (
    _infer_risk,
    _read_text,
    get_best_practices_doc_collection,
    ingest_best_practices_docs,
    CHROMA_DIR,
    DOC_COLLECTION,
)


class TestInferRisk:
    """Tests for _infer_risk function."""

    def test_infer_policy_risk(self):
        """Test inferring policy risk."""
        text = "Company policy requires code review"
        risk = _infer_risk(text)
        assert risk == "policy"

    def test_infer_security_risk(self):
        """Test inferring security risk."""
        text = "Authentication must use strong passwords"
        risk = _infer_risk(text)
        assert risk == "security"

    def test_infer_security_with_token(self):
        """Test inferring security with token keyword."""
        text = "Store API tokens securely"
        risk = _infer_risk(text)
        assert risk == "security"

    def test_infer_general_risk(self):
        """Test inferring general risk."""
        text = "Update documentation formatting"
        risk = _infer_risk(text)
        assert risk == "general"

    def test_infer_risk_case_insensitive(self):
        """Test risk inference is case insensitive."""
        text1 = "SECURITY policy"
        text2 = "security policy"
        assert _infer_risk(text1) == _infer_risk(text2)

    def test_infer_risk_empty_text(self):
        """Test inferring risk from empty text."""
        risk = _infer_risk("")
        assert risk == "general"


class TestReadText:
    """Tests for _read_text function."""

    def test_read_markdown_file(self, temp_dir):
        """Test reading markdown file."""
        file = temp_dir / "test.md"
        content = "# Test Document\n\nThis is a test."
        file.write_text(content, encoding="utf-8")
        
        result = _read_text(file)
        assert result == content

    def test_read_txt_file(self, temp_dir):
        """Test reading text file."""
        file = temp_dir / "test.txt"
        content = "Plain text content"
        file.write_text(content, encoding="utf-8")
        
        result = _read_text(file)
        assert result == content

    @patch("best_practices_docs.PdfReader")
    def test_read_pdf_file(self, mock_pdf_reader, temp_dir):
        """Test reading PDF file."""
        file = temp_dir / "test.pdf"
        file.touch()
        
        # Mock PDF reader
        mock_page = Mock()
        mock_page.extract_text.return_value = "PDF content"
        mock_reader_instance = Mock()
        mock_reader_instance.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader_instance
        
        result = _read_text(file)
        assert result == "PDF content"

    @patch("best_practices_docs.PdfReader", None)
    def test_read_pdf_without_pypdf2(self, temp_dir):
        """Test reading PDF without PyPDF2 installed."""
        file = temp_dir / "test.pdf"
        file.touch()
        
        with pytest.raises(RuntimeError, match="PyPDF2 is required"):
            _read_text(file)

    def test_read_unsupported_file_type(self, temp_dir):
        """Test reading unsupported file type returns empty string."""
        file = temp_dir / "test.json"
        file.write_text('{"key": "value"}')
        
        result = _read_text(file)
        assert result == ""

    def test_read_file_with_encoding_errors(self, temp_dir):
        """Test reading file with encoding errors."""
        file = temp_dir / "test.txt"
        # Write binary data that may cause encoding issues
        file.write_bytes(b'\xff\xfe invalid utf-8 \x80')
        
        # Should handle errors gracefully
        result = _read_text(file)
        # Result may be empty or partial depending on error handling
        assert isinstance(result, str)


class TestGetBestPracticesDocCollection:
    """Tests for get_best_practices_doc_collection function."""

    @patch("best_practices_docs.chromadb.PersistentClient")
    def test_get_doc_collection(self, mock_client_class):
        """Test getting doc collection."""
        mock_client = Mock()
        mock_collection = Mock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_class.return_value = mock_client
        
        collection = get_best_practices_doc_collection()
        
        mock_client.get_or_create_collection.assert_called_once_with(
            name=DOC_COLLECTION
        )
        assert collection == mock_collection


class TestIngestBestPracticeDocs:
    """Tests for ingest_best_practices_docs function."""

    def test_ingest_markdown_docs(self, temp_dir, capsys):
        """Test ingesting markdown documents."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        
        # Create markdown files
        (docs_folder / "guide.md").write_text("# Security Guide\n\nUse strong auth.")
        (docs_folder / "policy.md").write_text("# Policy\n\nCode review required.")
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        # Should have called upsert
        mock_collection.upsert.assert_called_once()
        
        # Check arguments
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["documents"]) == 2
        assert len(call_kwargs["ids"]) == 2
        
        # Check output
        captured = capsys.readouterr()
        assert "Ingested 2 documents" in captured.out

    def test_ingest_nested_docs(self, temp_dir, capsys):
        """Test ingesting documents from nested folders."""
        docs_folder = temp_dir / "docs"
        subfolder = docs_folder / "subfolder"
        subfolder.mkdir(parents=True)
        
        (docs_folder / "root.md").write_text("Root doc")
        (subfolder / "nested.md").write_text("Nested doc")
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["documents"]) == 2

    def test_ingest_only_supported_formats(self, temp_dir):
        """Test only supported file formats are ingested."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        
        # Create various files
        (docs_folder / "doc.md").write_text("Markdown")
        (docs_folder / "doc.txt").write_text("Text")
        (docs_folder / "script.py").write_text("# Python code")
        (docs_folder / "data.json").write_text('{"key": "value"}')
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        # Only .md and .txt should be ingested
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["documents"]) == 2

    def test_ingest_skip_empty_files(self, temp_dir):
        """Test empty files are skipped."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        
        (docs_folder / "content.md").write_text("Has content")
        (docs_folder / "empty.md").write_text("")
        (docs_folder / "whitespace.txt").write_text("   \n  ")
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        # Only file with content should be ingested
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["documents"]) == 1

    def test_ingest_metadata_structure(self, temp_dir):
        """Test metadata is properly structured."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        
        (docs_folder / "security.md").write_text("Security doc with auth keyword")
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        call_kwargs = mock_collection.upsert.call_args[1]
        metadata = call_kwargs["metadatas"][0]
        
        assert metadata["source"] == "company_docs"
        assert metadata["path"] == "security.md"
        assert metadata["kind"] == "policy"
        assert "risk_domain" in metadata
        assert "tags" in metadata

    def test_ingest_nonexistent_folder(self):
        """Test ingesting from nonexistent folder raises error."""
        with pytest.raises(FileNotFoundError):
            ingest_best_practices_docs(Path("/nonexistent/folder"), "source")

    def test_ingest_no_documents(self, temp_dir, capsys):
        """Test ingesting when no documents found."""
        docs_folder = temp_dir / "empty_docs"
        docs_folder.mkdir()
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        # Should not call upsert
        mock_collection.upsert.assert_not_called()
        
        # Should print message
        captured = capsys.readouterr()
        assert "No documents found" in captured.out

    def test_ingest_handle_read_errors(self, temp_dir, capsys):
        """Test handling errors when reading files."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        
        # Create a file that will cause an error
        error_file = docs_folder / "error.md"
        error_file.write_text("Content")
        
        mock_collection = Mock()
        
        with patch("best_practices_docs._read_text", side_effect=Exception("Read error")):
            with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
                ingest_best_practices_docs(docs_folder, "company_docs")
        
        # Should skip the errored file
        captured = capsys.readouterr()
        assert "Skipping" in captured.out

    def test_ingest_generates_unique_ids(self, temp_dir):
        """Test unique document IDs are generated."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        
        (docs_folder / "doc1.md").write_text("Doc 1")
        (docs_folder / "doc2.md").write_text("Doc 2")
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        call_kwargs = mock_collection.upsert.call_args[1]
        ids = call_kwargs["ids"]
        
        # IDs should be unique
        assert len(ids) == len(set(ids))
        # IDs should contain source name
        assert all("company_docs:" in id for id in ids)

    @patch("best_practices_docs.PdfReader")
    def test_ingest_pdf_documents(self, mock_pdf_reader, temp_dir):
        """Test ingesting PDF documents."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        
        pdf_file = docs_folder / "document.pdf"
        pdf_file.touch()
        
        # Mock PDF reader
        mock_page = Mock()
        mock_page.extract_text.return_value = "PDF content"
        mock_reader_instance = Mock()
        mock_reader_instance.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader_instance
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["documents"]) == 1
        assert "PDF content" in call_kwargs["documents"][0]

    def test_ingest_skip_directories(self, temp_dir):
        """Test that directories are skipped."""
        docs_folder = temp_dir / "docs"
        docs_folder.mkdir()
        subfolder = docs_folder / "subfolder"
        subfolder.mkdir()
        
        # Create file with .md directory name (edge case)
        (docs_folder / "file.md").write_text("Content")
        
        mock_collection = Mock()
        
        with patch("best_practices_docs.get_best_practices_doc_collection", return_value=mock_collection):
            ingest_best_practices_docs(docs_folder, "company_docs")
        
        # Only the file should be ingested, not the directory
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["documents"]) == 1
