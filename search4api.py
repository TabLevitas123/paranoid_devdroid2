import os
import re
import json
from urllib.parse import urlparse
import logging

class FindAPI:
    def __init__(self, directory):
        self.directory = directory
        self.api_calls = set()
        self.api_details = {}

    def search_codebase(self):
        # Expanded list of search terms
        api_pattern = re.compile(r'\b(|endpoint|api_endpoint|access_token|auth_token|client_id|client_secret|bearer_token|api_url|base_url)\b', re.IGNORECASE)
        for root, dirs, files in os.walk(self.directory):
            # Skip hidden directories and 'myenv' directory
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'myenv']
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r', errors='ignore') as f:
                        for line_number, line in enumerate(f, 1):
                            matches = api_pattern.findall(line)
                            if matches:
                                for match in matches:
                                    print(f"Found API term '{match}' in file: {file_path}, line: {line_number}")
                                self.api_calls.update(matches)
                                self.extract_api_details(line, file_path, line_number)

    def extract_api_details(self, content, file_path, line_number):
        # Example pattern to find API endpoints (you may need to adjust this based on your codebase)
        endpoint_pattern = re.compile(r'(https?://[^\s]+)')
        endpoints = endpoint_pattern.findall(content)
        for endpoint in endpoints:
            api_name = self.infer_api_name(endpoint, file_path, line_number)
            if api_name:
                print(f"Found API endpoint '{endpoint}' in file: {file_path}, line: {line_number}")
                self.api_details[api_name] = endpoint

    def infer_api_name(self, endpoint, file_path, line_number):
        # Extract the root domain name from the endpoint URL
        try:
            parsed_url = urlparse(endpoint)
            domain = parsed_url.netloc
            # Remove common subdomains like 'api', 'www', etc.
            domain_parts = domain.split('.')
            if len(domain_parts) > 2:
                domain = '.'.join(domain_parts[-2:])
            return domain.split('.')[0]
        except ValueError:
            logging.error(f"Invalid URL encountered in {file_path}, line: {line_number}: {endpoint}")
            return None

    def write_results(self):
        with open('api_names.txt', 'w') as f:
            for api_name in self.api_calls:
                f.write(f"{api_name}\n")

        with open('api_details.json', 'w') as f:
            json.dump(self.api_details, f, indent=4)

    def run(self):
        self.search_codebase()
        self.write_results()

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    directory = '/workspaces/paranoid_devdroid2'  # Set the directory to search
    finder = FindAPI(directory)
    finder.run()