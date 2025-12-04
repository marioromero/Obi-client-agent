import requests
import json

def test_standardization():
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
                
                # Verify Legacy Field (String)
                structure_json = draft.get("structure_json")
                print(f"Legacy 'structure_json' type: {type(structure_json)}")
                if isinstance(structure_json, str):
                    print("SUCCESS: Legacy field preserved.")
                else:
                    print("FAILURE: Legacy field changed type!")

                # Verify New Standard Field (Object)
                structure = draft.get("structure")
                print(f"New 'structure' type: {type(structure)}")
                if isinstance(structure, (list, dict)):
                    print("SUCCESS: New standard field present and parsed.")
                else:
                    print("FAILURE: New standard field missing or incorrect type.")
                    
            else:
                print("API returned status=False")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {str(e)}")

if __name__ == "__main__":
    test_standardization()
