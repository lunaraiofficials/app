import requests
import sys
import json
from datetime import datetime
import uuid

class SkillBuilderAPITester:
    def __init__(self, base_url="https://skillcraft-20.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.resume_id = None
        self.job_id = None
        self.application_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    # For form data with files
                    headers.pop('Content-Type', None)  # Let requests set it
                    response = requests.post(url, data=data, files=files, headers=headers)
                elif isinstance(data, dict) and any(isinstance(v, str) and '\n' in v for v in data.values()):
                    # For form data (like resume content)
                    headers.pop('Content-Type', None)
                    response = requests.post(url, data=data, headers=headers)
                else:
                    response = requests.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json()
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_signup(self):
        """Test user signup"""
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        success, response = self.run_test(
            "User Signup",
            "POST",
            "auth/signup",
            200,
            data={
                "email": test_email,
                "password": "TestPass123!",
                "full_name": "Test User"
            }
        )
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response['user']['id']
            print(f"   User ID: {self.user_id}")
            return True
        return False

    def test_login(self):
        """Test user login with existing credentials"""
        # First create a user
        test_email = f"login_test_{uuid.uuid4().hex[:8]}@example.com"
        signup_success, signup_response = self.run_test(
            "Signup for Login Test",
            "POST",
            "auth/signup",
            200,
            data={
                "email": test_email,
                "password": "TestPass123!",
                "full_name": "Login Test User"
            }
        )
        
        if not signup_success:
            return False
            
        # Now test login
        success, response = self.run_test(
            "User Login",
            "POST",
            "auth/login",
            200,
            data={
                "email": test_email,
                "password": "TestPass123!"
            }
        )
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response['user']['id']
            return True
        return False

    def test_get_me(self):
        """Test get current user"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        return success

    def test_resume_analyze(self):
        """Test resume ATS analysis"""
        sample_resume = """
        John Doe
        Software Engineer
        
        Experience:
        - 3 years at TechCorp as Frontend Developer
        - Built React applications
        - Worked with JavaScript, HTML, CSS
        
        Skills:
        - React, JavaScript, Python
        - Git, Docker
        
        Education:
        - BS Computer Science, University XYZ
        """
        
        success, response = self.run_test(
            "Resume ATS Analysis",
            "POST",
            "resumes/analyze",
            200,
            data={"resume_content": sample_resume}
        )
        if success:
            print(f"   ATS Score: {response.get('score', 'N/A')}")
        return success

    def test_job_match(self):
        """Test job matching"""
        sample_resume = "Software Engineer with React and JavaScript experience"
        sample_job = "Looking for Frontend Developer with React, JavaScript, and TypeScript skills"
        
        success, response = self.run_test(
            "Job Matching",
            "POST",
            "resumes/match-job",
            200,
            data={
                "resume_content": sample_resume,
                "job_description": sample_job
            }
        )
        if success:
            print(f"   Match Percentage: {response.get('match_percentage', 'N/A')}%")
        return success

    def test_resume_rewrite(self):
        """Test resume rewriting"""
        sample_resume = "I worked at a company doing software development"
        
        success, response = self.run_test(
            "Resume Rewriting",
            "POST",
            "resumes/rewrite",
            200,
            data={
                "resume_content": sample_resume,
                "tone": "professional"
            }
        )
        if success:
            print(f"   Rewritten length: {len(response.get('rewritten_content', ''))} chars")
        return success

    def test_create_resume(self):
        """Test creating a resume"""
        success, response = self.run_test(
            "Create Resume",
            "POST",
            "resumes",
            200,
            data={
                "title": "My Test Resume",
                "content": "Test resume content for API testing"
            }
        )
        if success and 'id' in response:
            self.resume_id = response['id']
            print(f"   Resume ID: {self.resume_id}")
        return success

    def test_get_resumes(self):
        """Test getting user resumes"""
        success, response = self.run_test(
            "Get User Resumes",
            "GET",
            "resumes",
            200
        )
        if success:
            print(f"   Found {len(response)} resumes")
        return success

    def test_get_resume_by_id(self):
        """Test getting specific resume"""
        if not self.resume_id:
            print("❌ Skipped - No resume ID available")
            return False
            
        success, response = self.run_test(
            "Get Resume by ID",
            "GET",
            f"resumes/{self.resume_id}",
            200
        )
        return success

    def test_get_jobs(self):
        """Test getting job listings"""
        success, response = self.run_test(
            "Get Job Listings",
            "GET",
            "jobs",
            200
        )
        if success and len(response) > 0:
            self.job_id = response[0]['id']
            print(f"   Found {len(response)} jobs")
            print(f"   First job ID: {self.job_id}")
        return success

    def test_get_job_by_id(self):
        """Test getting specific job"""
        if not self.job_id:
            print("❌ Skipped - No job ID available")
            return False
            
        success, response = self.run_test(
            "Get Job by ID",
            "GET",
            f"jobs/{self.job_id}",
            200
        )
        return success

    def test_create_application(self):
        """Test creating job application"""
        if not self.job_id or not self.resume_id:
            print("❌ Skipped - Missing job ID or resume ID")
            return False
            
        success, response = self.run_test(
            "Create Job Application",
            "POST",
            "applications",
            200,
            data={
                "job_id": self.job_id,
                "resume_id": self.resume_id,
                "cover_letter": "I am interested in this position..."
            }
        )
        if success and 'id' in response:
            self.application_id = response['id']
            print(f"   Application ID: {self.application_id}")
        return success

    def test_get_applications(self):
        """Test getting user applications"""
        success, response = self.run_test(
            "Get User Applications",
            "GET",
            "applications",
            200
        )
        if success:
            print(f"   Found {len(response)} applications")
        return success

    def test_get_templates(self):
        """Test getting resume templates"""
        success, response = self.run_test(
            "Get Resume Templates",
            "GET",
            "templates",
            200
        )
        if success:
            print(f"   Found {len(response)} templates")
        return success

    def test_delete_resume(self):
        """Test deleting a resume"""
        if not self.resume_id:
            print("❌ Skipped - No resume ID available")
            return False
            
        success, response = self.run_test(
            "Delete Resume",
            "DELETE",
            f"resumes/{self.resume_id}",
            200
        )
        return success

def main():
    print("🚀 Starting Skill Builder API Tests")
    print("=" * 50)
    
    tester = SkillBuilderAPITester()
    
    # Test sequence
    tests = [
        ("Authentication", [
            tester.test_signup,
            tester.test_login,
            tester.test_get_me,
        ]),
        ("AI Features", [
            tester.test_resume_analyze,
            tester.test_job_match,
            tester.test_resume_rewrite,
        ]),
        ("Resume Management", [
            tester.test_create_resume,
            tester.test_get_resumes,
            tester.test_get_resume_by_id,
        ]),
        ("Jobs & Applications", [
            tester.test_get_jobs,
            tester.test_get_job_by_id,
            tester.test_create_application,
            tester.test_get_applications,
        ]),
        ("Templates", [
            tester.test_get_templates,
        ]),
        ("Cleanup", [
            tester.test_delete_resume,
        ])
    ]
    
    for category, test_functions in tests:
        print(f"\n📋 {category} Tests")
        print("-" * 30)
        for test_func in test_functions:
            test_func()
    
    # Print final results
    print(f"\n📊 Test Results")
    print("=" * 50)
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Tests Failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success Rate: {(tester.tests_passed / tester.tests_run * 100):.1f}%")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())