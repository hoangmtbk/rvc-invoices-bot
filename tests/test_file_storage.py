from unittest.mock import MagicMock, patch


def test_build_filename_pdf():
    from file_storage import build_filename
    assert build_filename("0310674520", "000123", "20260429", "pdf") == \
        "0310674520_000123_20260429.pdf"


def test_build_filename_xml():
    from file_storage import build_filename
    assert build_filename("0310674520", "000456", "20260429", "xml") == \
        "0310674520_000456_20260429.xml"


def test_build_filename_empty_fields():
    from file_storage import build_filename
    assert build_filename("", "", "", "pdf") == "unknown_unknown_00000000.pdf"


def test_upload_file_returns_url():
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True

    with patch("file_storage._get_client", return_value=mock_client), \
         patch("file_storage.MINIO_BUCKET", "rvc-invoices"), \
         patch("file_storage.MINIO_PUBLIC_URL", "https://rvc-s3.rvctel.vn"):
        import importlib
        import file_storage
        importlib.reload(file_storage)
        url = file_storage.upload_file(
            b"data", "0310674520_000123_20260429.pdf", "application/pdf"
        )

    assert url == "https://rvc-s3.rvctel.vn/rvc-invoices/0310674520_000123_20260429.pdf"
    mock_client.put_object.assert_called_once()


def test_upload_file_creates_bucket_when_missing():
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = False

    with patch("file_storage._get_client", return_value=mock_client), \
         patch("file_storage.MINIO_BUCKET", "rvc-invoices"), \
         patch("file_storage.MINIO_PUBLIC_URL", "https://rvc-s3.rvctel.vn"):
        import importlib
        import file_storage
        importlib.reload(file_storage)
        file_storage.upload_file(b"data", "test.pdf", "application/pdf")

    mock_client.make_bucket.assert_called_once_with("rvc-invoices")
    mock_client.set_bucket_policy.assert_called_once()
