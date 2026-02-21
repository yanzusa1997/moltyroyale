#!/usr/bin/env python3
"""
Debug script to test API connectivity
"""

import requests
import json
from datetime import datetime, timezone

BASE_URL = "https://mort-royal-production.up.railway.app/api"

def test_api():
    """Test API endpoints"""
    print(f"Testing API at {BASE_URL}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("-" * 50)
    
    # Test 1: Create account
    print("Test 1: Create account")
    try:
        response = requests.post(
            f"{BASE_URL}/accounts",
            json={"name": "DebugBot"},
            headers={"Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("-" * 50)
    
    # Test 2: Get waiting games
    print("Test 2: Get waiting games")
    try:
        response = requests.get(f"{BASE_URL}/games?status=waiting")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
