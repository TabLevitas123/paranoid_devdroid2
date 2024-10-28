# scripts/performance_testing.py

"""
Performance Testing Module

This module conducts performance testing on the deployed machine learning model API.
It evaluates the model's responsiveness, throughput, and accuracy under various conditions.
"""

import os
import logging
import requests
import json
import time
from typing import Dict, Any, List
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure Logging
logging.basicConfig(
    filename='logs/performance_testing.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class PerformanceTester:
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the PerformanceTester with configuration parameters.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing API endpoints and test parameters.
        """
        self.api_url = config.get('api_url')
        self.predict_endpoint = config.get('predict_endpoint', '/predict')
        self.health_endpoint = config.get('health_endpoint', '/health')
        self.test_data_path = config.get('test_data_path')
        self.concurrency_levels = config.get('concurrency_levels', [1, 5, 10, 20])
        self.requests_per_level = config.get('requests_per_level', 100)
        self.results = []

    def load_test_data(self) -> pd.DataFrame:
        """
        Loads test data from the specified CSV file.

        Returns:
            pd.DataFrame: Test dataset.

        Raises:
            FileNotFoundError: If the test data file does not exist.
            pd.errors.ParserError: If the file cannot be parsed as CSV.
        """
        if not os.path.exists(self.test_data_path):
            logger.error(f"Test data file not found at {self.test_data_path}")
            raise FileNotFoundError(f"Test data file not found at {self.test_data_path}")
        try:
            data = pd.read_csv(self.test_data_path)
            logger.info(f"Loaded test data with shape {data.shape} from {self.test_data_path}")
            return data
        except pd.errors.ParserError as e:
            logger.error(f"Error parsing CSV file: {e}")
            raise

    def health_check(self) -> bool:
        """
        Checks the health of the deployed API.

        Returns:
            bool: True if the API is healthy, False otherwise.
        """
        try:
            response = requests.get(f"{self.api_url}{self.health_endpoint}", timeout=5)
            if response.status_code == 200:
                logger.info("Health check passed")
                return True
            else:
                logger.warning(f"Health check failed with status code {response.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"Health check request failed: {e}")
            return False

    def send_prediction_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a prediction request to the API.

        Args:
            payload (Dict[str, Any]): The input features for prediction.

        Returns:
            Dict[str, Any]: The API's response.
        """
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(
                f"{self.api_url}{self.predict_endpoint}",
                headers=headers,
                data=json.dumps({'features': payload}),
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Received response: {result}")
            return result
        except requests.RequestException as e:
            logger.error(f"Prediction request failed: {e}")
            return {'error': str(e)}

    def run_load_test(self, concurrency: int, total_requests: int, test_payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Runs a load test with specified concurrency and total requests.

        Args:
            concurrency (int): Number of concurrent threads.
            total_requests (int): Total number of prediction requests.
            test_payloads (List[Dict[str, Any]]): List of payloads for predictions.

        Returns:
            Dict[str, Any]: Aggregated results of the load test.
        """
        start_time = time.time()
        successful_requests = 0
        failed_requests = 0
        response_times = []
        predictions_correct = 0  # Placeholder for correctness, requires ground truth

        def task(payload):
            nonlocal successful_requests, failed_requests, predictions_correct
            start = time.time()
            response = self.send_prediction_request(payload)
            end = time.time()
            response_time = end - start
            response_times.append(response_time)
            if 'error' not in response:
                successful_requests += 1
                # Implement correctness check if ground truth is available
                # For example:
                # if response['prediction'] == payload['actual']:
                #     predictions_correct += 1
            else:
                failed_requests += 1

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(task, payload) for payload in test_payloads[:total_requests]]
            for future in as_completed(futures):
                pass  # All handling is done in the task function

        end_time = time.time()
        total_time = end_time - start_time
        average_response_time = sum(response_times) / len(response_times) if response_times else 0

        result = {
            'concurrency_level': concurrency,
            'total_requests': total_requests,
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'average_response_time_sec': average_response_time,
            'total_time_sec': total_time,
            # 'accuracy': predictions_correct / successful_requests if successful_requests else 0
        }

        logger.info(f"Load Test Results for concurrency {concurrency}: {result}")
        return result

    def execute_tests(self):
        """
        Executes performance tests across different concurrency levels.
        """
        if not self.health_check():
            logger.error("API is not healthy. Aborting performance tests.")
            raise ConnectionError("API is not healthy.")

        test_data = self.load_test_data()
        test_payloads = test_data.to_dict(orient='records')

        for concurrency in self.concurrency_levels:
            result = self.run_load_test(
                concurrency=concurrency,
                total_requests=self.requests_per_level,
                test_payloads=test_payloads
            )
            self.results.append(result)

        logger.info("Performance testing completed successfully")
        self.save_results()

    def save_results(self):
        """
        Saves the performance testing results to a JSON file.
        """
        os.makedirs('results', exist_ok=True)
        results_path = os.path.join('results', 'performance_testing_results.json')
        with open(results_path, 'w') as f:
            json.dump(self.results, f, indent=4)
        logger.info(f"Saved performance testing results to {results_path}")

def main():
    # Configuration Parameters
    config = {
        'api_url': 'http://localhost:8000',
        'predict_endpoint': '/predict',
        'health_endpoint': '/health',
        'test_data_path': 'data/test/test_data.csv',
        'concurrency_levels': [1, 5, 10, 20],
        'requests_per_level': 100
    }

    tester = PerformanceTester(config)
    try:
        tester.execute_tests()
    except Exception as e:
        logger.exception(f"Performance testing failed: {e}")

if __name__ == "__main__":
    main()
