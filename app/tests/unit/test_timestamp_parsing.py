import pytest
from app.schemas.generation import TaipowerResponse

def test_taipower_response_parsing():
    raw_json = """
    {
        "": "2024-01-08 13:00",
        "aaData": []
    }
    """
    try:
        data = TaipowerResponse.model_validate_json(raw_json)
        print(f"Parsed Timestamp: '{data.timestamp}'")
        assert data.timestamp == "2024-01-08 13:00"
    except Exception as e:
        print(f"Parsing failed: {e}")
        raise e

if __name__ == "__main__":
    test_taipower_response_parsing()
