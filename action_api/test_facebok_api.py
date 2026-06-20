import requests
import time
import json

# Define the base URL for the Facebook Agent API
# By default, facebook_server.py runs on port 8000
BASE_URL = "http://127.0.0.1:8000"

def print_response(name, response):
    print(f"\n{'='*10} Testing: {name} {'='*10}")
    print(f"Status Code: {response.status_code}")
    try:
        data = response.json()
        
        # Save extraction to a file for review
        filename = f"exports/extraction_{name.replace(' ', '_').lower()}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved extraction to {filename}")

        # Pretty print JSON, but truncate long outputs for readability
        formatted = json.dumps(data, indent=2)
        if len(formatted) > 1000:
            print(formatted[:1000] + "\n... [TRUNCATED] ...")
        else:
            print(formatted)
    except Exception as e:
        print(f"Failed to parse JSON response. Raw text:\n{response.text}")


def test_init():
    url = f"{BASE_URL}/api/init"
    print(f"Sending POST to {url}...")
    response = requests.post(url)
    print_response("Initialize Browser", response)
    # Give it a bit of time to settle after logging in
    time.sleep(2)


def test_scrape_search():
    url = f"{BASE_URL}/api/scrape/search"
    payload = {
        "query": "Flat Bangalore",
        "max_posts": 10,     # Keep small for quick testing
        "max_scrolls": 10
    }
    print(f"Sending POST to {url} with payload {payload}...")
    response = requests.post(url, json=payload)
    print_response("Scrape Search", response)
    time.sleep(2)


def test_scrape_url():
    url = f"{BASE_URL}/api/scrape/url"
    payload = {
        "url": "https://www.facebook.com/groups/machinelearning",
        "max_posts": 2,
        "max_scrolls": 2
    }
    print(f"Sending POST to {url} with payload {payload}...")
    response = requests.post(url, json=payload)
    print_response("Scrape URL", response)
    time.sleep(2)


def test_click_action():
    url = f"{BASE_URL}/api/action/click"
    # Assuming there's a "See more" or "See More" button somewhere on the page
    payload = {
        "text": "See more"
    }
    print(f"Sending POST to {url} with payload {payload}...")
    response = requests.post(url, json=payload)
    print_response("Click Element", response)
    time.sleep(2)


def test_scrape_home():
    url = f"{BASE_URL}/api/scrape/home"
    payload = {
        "max_posts": 10,
        "max_scrolls": 10
    }
    print(f"Sending POST to {url} with payload {payload}...")
    response = requests.post(url, json=payload)
    print_response("Scrape Home", response)
    time.sleep(2)




def test_close():
    url = f"{BASE_URL}/api/close"
    print(f"Sending POST to {url}...")
    response = requests.post(url)
    print_response("Close Browser", response)


def main():
    print("Starting API Tests. Ensure facebook_server.py is running!")
    try:
        # Check if server is alive by making a simple request
        requests.get(BASE_URL)
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {BASE_URL}. Is the server running?")
        return

    # Run the tests in sequence
    test_init()
    # test_scrape_home()
    test_scrape_search()
    # test_scrape_url()  # Optional: uncomment to test specific URL scraping
    # test_click_action()
    
    # Finally, close the browser (commented out by default so you can inspect)
    # test_close()

if __name__ == "__main__":
    main()
