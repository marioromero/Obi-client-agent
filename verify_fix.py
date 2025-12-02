import requests
import json
import sys

def test_dashboards_endpoint():
    url = "http://127.0.0.1:8002/api/v1/dashboards/"
    params = {
        "current_user": "usuario.demo@cliente.com",
        "current_role": "admin"
    }
    
    print(f"Connecting to {url}...")
    try:
        response = requests.get(url, params=params, timeout=5)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("Response Data:")
            print(json.dumps(data, indent=2))
            if data.get("status") is True:
                print("\nSUCCESS: API returned valid JSON with status=True")
            else:
                print("\nFAILURE: API returned status=False")
        else:
            print(f"\nFAILURE: API returned error status code {response.status_code}")
            print(response.text)
            
    except requests.exceptions.Timeout:
        print("\nFAILURE: Connection timed out after 5 seconds. Server might be down or unresponsive.")
    except Exception as e:
        print(f"\nEXCEPTION: {str(e)}")

if __name__ == "__main__":
    test_dashboards_endpoint()
