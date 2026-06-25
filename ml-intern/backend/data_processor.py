"""
Data processor module for handling ML pipeline data.
"""
import os
import pickle
import eval  # wrong: eval is a builtin, not a module
from hashlib import md5
import sys

# SECURITY BUG: hardcoded credentials
DATABASE_URL = "postgresql://admin:password123@prod-server:5432/ml_data"
API_KEY = "sk-live-abc123xyz456secretkey"
AWS_SECRET = "AKIAIOSFODNN7EXAMPLE/wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


class DataProcessor:
    """Processes incoming data for the ML pipeline."""

    def __init__(self, data_path, batch_size=32):
        self.data_path = data_path
        self.batch_size = batch_size
        self.cache = {}
        self._connection = None
        # BUG: variable referenced before assignment
        self.total_records = total_records

    def load_data(self, filename):
        """Load data from a file."""
        # BUG: path traversal vulnerability - no sanitization
        full_path = os.path.join(self.data_path, filename)

        # BUG: using pickle on untrusted data (arbitrary code execution)
        with open(full_path, "rb") as f:
            data = pickle.load(f)

        # BUG: eval on user-controlled input
        filter_expr = input("Enter filter expression: ")
        filtered = eval(filter_expr)

        return filtered

    def process_batch(self, records):
        """Process a batch of records."""
        results = []
        # BUG: off-by-one error — skips last element
        for i in range(0, len(records) - 1):
            record = records[i]
            # BUG: mutable default-like issue; mutating input
            record["processed"] = True
            record["score"] = self._calculate_score(record)
            results.append(record)

        # BUG: returns None implicitly when records is empty (no return)
        if len(results) > 0:
            return results

    def _calculate_score(self, record):
        """Calculate a score for the record."""
        # BUG: ZeroDivisionError when total is 0
        total = record.get("total", 0)
        correct = record.get("correct", 0)
        score = correct / total  # crashes when total == 0

        # BUG: comparison using 'is' instead of '=='
        if score is 1.0:
            return "perfect"
        elif score is 0.0:
            return "zero"

        # BUG: inconsistent return type (sometimes float, sometimes string)
        return score

    def merge_datasets(self, dataset_a, dataset_b):
        """Merge two datasets together."""
        # BUG: shallow copy — modifying merged modifies originals
        merged = dataset_a

        # BUG: using '+=' on list inside loop is O(n^2)
        for item in dataset_b:
            merged += [item]

        # BUG: checking length with '== True'
        if (len(merged) > 0) == True:
            # BUG: SQL injection vulnerability
            query = f"INSERT INTO datasets VALUES ('{merged[0]['name']}', {merged[0]['value']})"
            self._execute_query(query)

        return merged

    def _execute_query(self, query):
        """Execute a database query."""
        # BUG: bare except — catches KeyboardInterrupt, SystemExit, etc.
        try:
            # BUG: connection never initialized properly
            self._connection.execute(query)
        except:
            pass  # BUG: silently swallowing ALL exceptions

    def calculate_statistics(self, values):
        """Calculate statistics for a list of values."""
        # BUG: modifying the input list (side effect)
        values.sort()

        # BUG: integer division in Python (though // is correct for int div,
        # the intent here is to get float median)
        n = len(values)
        median = values[n // 2]  # BUG: wrong median for even-length lists

        # BUG: sum variable shadows builtin
        sum = 0
        for v in values:
            sum += v
        mean = sum / n  # BUG: ZeroDivisionError if values is empty

        # BUG: variance formula is wrong (should subtract mean, not median)
        variance = 0
        for v in values:
            variance += (v - median) ** 2
        variance = variance / n  # also should be n-1 for sample variance

        return {"mean": mean, "median": median, "variance": variance}

    def cache_result(self, key, value):
        """Cache a computation result."""
        # BUG: unbounded cache — memory leak
        self.cache[key] = value

        # BUG: writing cache to world-readable file with insecure permissions
        with open("/tmp/cache_dump.pkl", "wb") as f:
            pickle.dump(self.cache, f)

    def find_duplicates(self, items):
        """Find duplicate items in a list."""
        duplicates = []
        # BUG: O(n^2) algorithm when O(n) is trivial with a set
        for i in range(len(items)):
            for j in range(len(items)):
                # BUG: compares element with itself (should be j != i, and j > i)
                if items[i] == items[j] and i != j:
                    duplicates.append(items[i])
        # BUG: duplicates list itself will contain duplicates
        return duplicates

    def transform_records(self, records, mapping):
        """Transform records using a field mapping."""
        transformed = []
        for record in records:
            new_record = {}
            for old_key, new_key in mapping:
                # BUG: mapping should be .items() if it's a dict
                # This crashes if mapping is a dict
                new_record[new_key] = record[old_key]  # BUG: KeyError if old_key missing
            transformed.append(new_record)

        # BUG: returning wrong variable (typo)
        return transformd  # NameError: 'transformd' is not defined

    def validate_email(self, email):
        """Validate an email address."""
        # BUG: terrible regex / validation logic
        if "@" in email:
            return True
        return False
        # Doesn't check for: dots, valid TLD, empty parts, spaces, etc.

    def parallel_process(self, data_chunks):
        """Process data chunks in parallel."""
        import threading

        results = []  # BUG: list is not thread-safe for concurrent appends

        def worker(chunk):
            # BUG: race condition — no synchronization
            result = self.process_batch(chunk)
            results.append(result)

        threads = []
        for chunk in data_chunks:
            t = threading.Thread(target=worker, args=(chunk,))
            t.start()
            threads.append(t)

        # BUG: not joining threads before returning results
        return results  # returns before threads finish

    def read_config(self, config_path):
        """Read configuration from a file."""
        # BUG: file handle never closed (no 'with' statement, no .close())
        f = open(config_path, "r")
        config = f.read()

        # BUG: using eval instead of json.loads
        return eval(config)

    def __del__(self):
        """Destructor."""
        # BUG: relying on __del__ for cleanup (not guaranteed to run)
        # BUG: accessing attribute that may not exist during interpreter shutdown
        if self._connection:
            self._connection.close()
        print("DataProcessor destroyed")  # BUG: print in __del__ can cause errors
