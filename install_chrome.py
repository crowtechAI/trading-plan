#!/usr/bin/env python3
"""
Script to manually install Chrome and ChromeDriver if system packages fail
"""
import os
import subprocess
import sys
import requests
import zipfile
import tempfile

def run_command(command, check=True):
    """Run a shell command"""
    try:
        result = subprocess.run(command, shell=True, check=check, 
                              capture_output=True, text=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {command}")
        print(f"Error: {e.stderr}")
        return False

def install_chrome_manually():
    """Install Chrome manually if package manager fails"""
    print("Attempting manual Chrome installation...")
    
    # Try to install Chrome via wget
    commands = [
        "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -",
        "echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' > /etc/apt/sources.list.d/google-chrome.list",
        "apt-get update",
        "apt-get install -y google-chrome-stable"
    ]
    
    for cmd in commands:
        if not run_command(cmd):
            print(f"Failed to execute: {cmd}")
            return False
    
    return True

def install_chromedriver():
    """Install ChromeDriver manually"""
    print("Installing ChromeDriver...")
    
    try:
        # Get latest ChromeDriver version
        version_response = requests.get("https://chromedriver.storage.googleapis.com/LATEST_RELEASE")
        version = version_response.text.strip()
        
        # Download ChromeDriver
        driver_url = f"https://chromedriver.storage.googleapis.com/{version}/chromedriver_linux64.zip"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "chromedriver.zip")
            
            # Download
            response = requests.get(driver_url)
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            # Extract
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Move to system path
            chromedriver_path = os.path.join(temp_dir, "chromedriver")
            run_command(f"chmod +x {chromedriver_path}")
            run_command(f"mv {chromedriver_path} /usr/local/bin/chromedriver")
            
        print("ChromeDriver installed successfully")
        return True
        
    except Exception as e:
        print(f"Failed to install ChromeDriver: {e}")
        return False

def main():
    """Main installation function"""
    print("Starting Chrome installation...")
    
    # Check if Chrome is already installed
    if run_command("which google-chrome", check=False):
        print("Chrome already installed")
    elif run_command("which chromium", check=False):
        print("Chromium already installed")
    else:
        print("No Chrome browser found, attempting installation...")
        if not install_chrome_manually():
            print("Failed to install Chrome")
            sys.exit(1)
    
    # Check if ChromeDriver is installed
    if not run_command("which chromedriver", check=False):
        if not install_chromedriver():
            print("Failed to install ChromeDriver")
            sys.exit(1)
    else:
        print("ChromeDriver already installed")
    
    print("Installation completed successfully!")

if __name__ == "__main__":
    main()
