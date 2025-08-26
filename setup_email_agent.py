#!/usr/bin/env python3
"""
Setup script for the email agent dependencies.
"""

import subprocess
import sys
import os

def run_command(command):
    """Run a shell command and return success status."""
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {command}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {command}")
        print(f"   Error: {e.stderr}")
        return False

def main():
    """Set up the email agent environment."""
    print("🚀 Setting up Email Agent dependencies...")
    
    # Install dependencies using uv (if available) or pip
    print("\n📦 Installing Python dependencies...")
    
    if os.path.exists("pyproject.toml"):
        # Try uv first
        if run_command("uv --version"):
            print("Using uv for dependency management...")
            success = run_command("uv sync")
        else:
            print("uv not found, using pip...")
            success = run_command("pip install -e .")
    else:
        print("Installing dependencies directly with pip...")
        success = run_command("pip install opperai pydantic google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    
    if not success:
        print("❌ Failed to install Python dependencies")
        return False
    
    print("\n✅ Dependencies installed successfully!")
    
    # Check for credentials
    print("\n🔐 Checking Gmail API setup...")
    
    if os.path.exists("credentials.json"):
        print("✅ Found credentials.json")
    else:
        print("❌ credentials.json not found")
        print("\nTo set up Gmail API access:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select existing one")
        print("3. Enable the Gmail API")
        print("4. Configure OAuth consent screen")
        print("5. Create OAuth 2.0 credentials (Desktop application)")
        print("6. Download credentials as 'credentials.json' in this directory")
    
    # Check for Opper API key
    print("\n🔑 Checking Opper API key...")
    
    if os.getenv("OPPER_API_KEY"):
        print("✅ Found OPPER_API_KEY environment variable")
    else:
        print("❌ OPPER_API_KEY environment variable not set")
        print("\nTo set up Opper API:")
        print("1. Get your API key from https://platform.opper.ai")
        print("2. Set the environment variable:")
        print("   export OPPER_API_KEY='your_api_key_here'")
        print("   Or add it to your shell profile (~/.bashrc, ~/.zshrc, etc.)")
    
    print("\n🎯 Setup complete! You can now run:")
    print("   python email_agent.py")
    
    return True

if __name__ == "__main__":
    main()
