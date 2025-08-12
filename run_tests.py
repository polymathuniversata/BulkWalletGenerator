#!/usr/bin/env python3
"""
Test runner for the Wallet Bot project.
Runs all tests with proper configuration and reporting.
"""
import sys
import subprocess
from pathlib import Path

def run_tests():
    """Run the test suite with comprehensive reporting."""
    project_root = Path(__file__).parent
    
    # Test categories
    test_categories = {
        "unit": ["tests/test_wallets.py", "tests/test_validators.py"],
        "error_handling": ["tests/test_error_handling.py"],
        "ui_flows": ["tests/test_ui_flows.py"],
        "integration": ["tests/test_integration.py"],
    }
    
    print("🧪 Running Wallet Bot Test Suite")
    print("=" * 50)
    
    all_passed = True
    results = {}
    
    for category, test_files in test_categories.items():
        print(f"\n📂 Running {category.upper()} tests...")
        
        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            "-v",
            "--tb=short",
            "--color=yes",
            *test_files
        ]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout per category
            )
            
            results[category] = {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
            if result.returncode == 0:
                print(f"✅ {category} tests PASSED")
            else:
                print(f"❌ {category} tests FAILED")
                all_passed = False
                
            # Show output for failed tests
            if result.returncode != 0 and result.stdout:
                print(f"Output:\n{result.stdout}")
                
        except subprocess.TimeoutExpired:
            print(f"⏰ {category} tests TIMED OUT")
            all_passed = False
        except Exception as e:
            print(f"💥 {category} tests ERROR: {e}")
            all_passed = False
    
    print("\n" + "=" * 50)
    
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\n✨ Your wallet bot is ready for production!")
    else:
        print("❌ SOME TESTS FAILED")
        print("\n🔍 Check the output above for details.")
        
        # Show summary of failures
        failed_categories = [cat for cat, res in results.items() if res.get("returncode", 1) != 0]
        if failed_categories:
            print(f"\n📋 Failed categories: {', '.join(failed_categories)}")
    
    return all_passed

def run_quick_tests():
    """Run only the fast unit tests for quick validation."""
    print("⚡ Running Quick Tests...")
    
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/test_wallets.py",
        "tests/test_validators.py",
        "-v", "--tb=line"
    ]
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    return result.returncode == 0

def run_coverage():
    """Run tests with coverage reporting."""
    print("📊 Running Tests with Coverage...")
    
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=src",
        "--cov-report=term-missing",
        "--cov-report=html",
        "tests/"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent)
        if result.returncode == 0:
            print("📈 Coverage report generated in htmlcov/")
        return result.returncode == 0
    except FileNotFoundError:
        print("❌ pytest-cov not installed. Run: pip install pytest-cov")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Wallet Bot tests")
    parser.add_argument("--quick", action="store_true", help="Run only quick unit tests")
    parser.add_argument("--coverage", action="store_true", help="Run tests with coverage")
    
    args = parser.parse_args()
    
    if args.quick:
        success = run_quick_tests()
    elif args.coverage:
        success = run_coverage()
    else:
        success = run_tests()
    
    sys.exit(0 if success else 1)