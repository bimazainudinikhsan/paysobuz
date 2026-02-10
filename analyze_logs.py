import json
import re

def analyze_logs(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            
        print(f"Loaded {len(logs)} log entries.")
        
        relevant_logs = []
        for entry in logs:
            url = entry.get('url', '')
            method = entry.get('method', '')
            
            # Filter out noise
            if not url or "sociabuzz.com" not in url:
                continue
            if any(x in url for x in ["cdn-cgi", "google", "facebook", "newrelic", "nr-data", "fonts", ".js", ".css", ".png", ".jpg", ".svg", ".woff"]):
                continue
                
            relevant_logs.append(entry)
            
        print(f"Found {len(relevant_logs)} relevant entries.\n")
        
        # specific_keywords = ["withdraw", "payout", "balance", "cairkan", "fund", "transaction"]
        
        for i, log in enumerate(relevant_logs):
            url = log.get('url', '')
            post_data = log.get('postData', '')
            
            # Print everything that looks like an API call (POST/PUT/DELETE or GET with query params)
            # especially if it relates to the dashboard or transactions
            # if "payment/send/create" in url:
            #      continue # We know these are payment creations, skip to reduce noise if we want to find withdrawals
            
            # Filter for payment creation and method selection
            if "donate/get-form-queue" not in url and "payment/send/create" not in url:
                continue

            print(f"--- Entry {i+1} ---")
            print(f"Method: {log.get('method')}")
            print(f"URL: {url}")
            
            if post_data:
                print(f"Post Data: {post_data}")
                
            headers = log.get('headers', {})
            print("\n")
            
    except Exception as e:
        print(f"Error analyzing logs: {e}")

if __name__ == "__main__":
    analyze_logs("api_logs.json")
