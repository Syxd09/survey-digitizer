import time
import os
import sys

start_time = time.time()
os.system("./.venv/bin/python scratch/test_api_endpoints.py")
end_time = time.time()

print(f"Total test suite execution time: {end_time - start_time:.2f} seconds")
