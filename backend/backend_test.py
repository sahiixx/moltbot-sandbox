import requests
import sys
from datetime import datetime

class MoltbotAPITester:
    def __init__(self, base_url="https://quickmolt.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.owner_token = None
        self.other_token = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        if headers is None:
            headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {response_data}")
                except:
                    print(f"   Response: {response.text[:200]}")
            else:
                self.tests_failed += 1
                self.failed_tests.append(name)
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Response: {response.text[:200]}")

            return success, response

        except requests.exceptions.Timeout:
            self.tests_failed += 1
            self.failed_tests.append(name)
            print(f"❌ Failed - Request timeout")
            return False, None
        except requests.exceptions.ConnectionError as e:
            self.tests_failed += 1
            self.failed_tests.append(name)
            print(f"❌ Failed - Connection error: {str(e)}")
            return False, None
        except Exception as e:
            self.tests_failed += 1
            self.failed_tests.append(name)
            print(f"❌ Failed - Error: {str(e)}")
            return False, None

    def test_root_endpoint(self):
        """Test root API endpoint"""
        success, response = self.run_test(
            "Root API Endpoint",
            "GET",
            "",
            200
        )
        return success

    def test_moltbot_status_initial(self):
        """Test Moltbot status endpoint (should not be running initially)"""
        success, response = self.run_test(
            "Moltbot Status (Initial)",
            "GET",
            "moltbot/status",
            200
        )
        if success:
            data = response.json()
            if not data.get('running'):
                print("   ✓ Moltbot is not running (expected)")
                return True
            else:
                print("   ⚠ Moltbot is already running")
                return True
        return False

    def test_moltbot_start_validation(self, token=None):
        """Test Moltbot start endpoint validation"""
        print("\n--- Testing Start Endpoint Validation ---")
        
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        # Test 1: Missing provider
        success1, _ = self.run_test(
            "Start without provider",
            "POST",
            "moltbot/start",
            422,  # Validation error
            data={"apiKey": "test-key-1234567890"},
            headers=headers
        )
        
        # Test 2: Invalid provider
        success2, _ = self.run_test(
            "Start with invalid provider",
            "POST",
            "moltbot/start",
            400,
            data={"provider": "invalid", "apiKey": "test-key-1234567890"},
            headers=headers
        )
        
        # Test 3: Short API key
        success3, _ = self.run_test(
            "Start with short API key",
            "POST",
            "moltbot/start",
            400,
            data={"provider": "anthropic", "apiKey": "short"},
            headers=headers
        )
        
        return success1 and success2 and success3

    def test_legacy_status_endpoints(self):
        """Test legacy status check endpoints"""
        print("\n--- Testing Legacy Status Endpoints ---")
        
        # Test POST /status
        success1, response = self.run_test(
            "Create Status Check",
            "POST",
            "status",
            200,
            data={"client_name": "test_client"}
        )
        
        # Test GET /status
        success2, _ = self.run_test(
            "Get Status Checks",
            "GET",
            "status",
            200
        )
        
        return success1 and success2

    def test_auth_unauthenticated(self):
        """Test that unauthenticated requests are rejected"""
        print("\n--- Testing Unauthenticated Access ---")
        
        # Test GET /auth/me without token
        success1, _ = self.run_test(
            "GET /auth/me (unauthenticated)",
            "GET",
            "auth/me",
            401
        )
        
        # Test POST /moltbot/start without token
        success2, _ = self.run_test(
            "POST /moltbot/start (unauthenticated)",
            "POST",
            "moltbot/start",
            401,
            data={"provider": "anthropic", "apiKey": "sk-ant-test-1234567890"}
        )
        
        # Test POST /moltbot/stop without token
        success3, _ = self.run_test(
            "POST /moltbot/stop (unauthenticated)",
            "POST",
            "moltbot/stop",
            401
        )
        
        # Test GET /moltbot/token without token
        success4, _ = self.run_test(
            "GET /moltbot/token (unauthenticated)",
            "GET",
            "moltbot/token",
            401
        )
        
        return success1 and success2 and success3 and success4

    def test_auth_with_token(self, token):
        """Test authenticated access with token"""
        print("\n--- Testing Authenticated Access ---")
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        # Test GET /auth/me with token
        success, response = self.run_test(
            "GET /auth/me (authenticated)",
            "GET",
            "auth/me",
            200,
            headers=headers
        )
        
        if success:
            data = response.json()
            if 'user_id' in data and 'email' in data:
                print("   ✓ User data returned correctly")
            else:
                print("   ⚠ User data missing expected fields")
        
        return success

    def test_moltbot_status_with_auth(self, token):
        """Test Moltbot status with authentication"""
        print("\n--- Testing Moltbot Status (Authenticated) ---")
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        success, response = self.run_test(
            "GET /moltbot/status (authenticated)",
            "GET",
            "moltbot/status",
            200,
            headers=headers
        )
        
        if success:
            data = response.json()
            print(f"   Running: {data.get('running')}")
            if data.get('running'):
                print(f"   Owner: {data.get('owner_user_id')}")
                print(f"   Is Owner: {data.get('is_owner')}")
        
        return success

    def test_logout(self, token):
        """Test logout endpoint"""
        print("\n--- Testing Logout ---")
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        success, response = self.run_test(
            "POST /auth/logout",
            "POST",
            "auth/logout",
            200,
            headers=headers
        )
        
        return success

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        print(f"Total Tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for test in self.failed_tests:
                print(f"   - {test}")
        
        print("="*60)

def main():
    print("="*60)
    print("🦞 MOLTBOT API TESTING WITH AUTHENTICATION")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tester = MoltbotAPITester()
    
    # Get test tokens from environment or use hardcoded test tokens
    import os
    owner_token = os.environ.get('TEST_OWNER_TOKEN', 'test_session_owner_1769688072511')
    other_token = os.environ.get('TEST_OTHER_TOKEN', 'test_session_other_1769688072511')
    
    print(f"\nUsing owner token: {owner_token[:20]}...")
    print(f"Using other token: {other_token[:20]}...")
    
    # Run tests
    print("\n--- Basic API Tests ---")
    tester.test_root_endpoint()
    
    print("\n--- Authentication Tests (Unauthenticated) ---")
    tester.test_auth_unauthenticated()
    
    print("\n--- Authentication Tests (With Token) ---")
    tester.test_auth_with_token(owner_token)
    
    print("\n--- Moltbot Status Tests ---")
    tester.test_moltbot_status_initial()
    tester.test_moltbot_status_with_auth(owner_token)
    
    print("\n--- Moltbot Start Validation Tests ---")
    tester.test_moltbot_start_validation()
    
    print("\n--- Legacy Endpoints Tests ---")
    tester.test_legacy_status_endpoints()
    
    print("\n--- Logout Test ---")
    tester.test_logout(owner_token)
    
    # Print summary
    tester.print_summary()
    
    # Return exit code
    return 0 if tester.tests_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
