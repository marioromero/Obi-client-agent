import requests
import json

def test_schema_draft():
    url = "http://127.0.0.1:8002/api/v1/schema/draft"
    params = {
        "connection_key": "traro_cases"
    }
    
    print(f"Connecting to {url}...")
    try:
        response = requests.get(url, params=params, timeout=5)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status"):
                draft = data.get("data", {})
                structure = draft.get("structure_json")
                print(f"Type of structure_json: {type(structure)}")
                
                if isinstance(structure, (list, dict)):
                     print("\nSUCCESS: structure_json is correctly parsed as an object/list.")
                     # print(json.dumps(structure, indent=2)[:500] + "...")
                else:
                     print("\nFAILURE: structure_json is still a string or unknown type.")
            else:
                print("API returned status=False")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {str(e)}")

if __name__ == "__main__":
    test_schema_draft()
