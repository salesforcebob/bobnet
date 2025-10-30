from app.worker import process_mail


def test_plus_tag_extraction():
    job = {
        "message_id": "abc",
        "to": "c96be77c591e99f5c6bf+testbot1@cloudmailin.net",
        "html": "<html></html>",
    }
    result = process_mail(job)
    assert result["customer_tag"] == "testbot1"
