import os
import sys
import time
import json
import pyotp
from datetime import datetime
from playwright.sync_api import sync_playwright

def save_status(status, error_msg=None):
    status_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookie_status.json')
    data = {
        "last_attempt_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_success_time": None,
        "status": status,
        "error_message": error_msg
    }
    
    # Try to load existing file to preserve last_success_time
    if os.path.exists(status_path):
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                data["last_success_time"] = old_data.get("last_success_time")
        except Exception:
            pass
            
    if status == "success":
        data["last_success_time"] = data["last_attempt_time"]
        
    try:
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving cookie status file: {e}")
        
    return data

def sync_to_web_service(sync_url, sync_token, cookies_content, status_content):
    if not sync_url or not sync_token:
        print("Skipping web service sync (WEB_SERVICE_URL or COOKIE_SYNC_TOKEN not set).")
        return
        
    print(f"Syncing cookies to web service at: {sync_url}...")
    import urllib.request
    
    try:
        url = f"{sync_url.rstrip('/')}/api/cookies/sync"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {sync_token}"
        }
        payload = {
            "cookies_content": cookies_content,
            "status_content": status_content
        }
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Sync response: {resp.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error syncing cookies to web service: {e}")

def main():
    # Load credentials from environment or local secrets.json file
    secrets = {}
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'secrets.json')
    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, 'r', encoding='utf-8') as f:
                secrets = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load secrets.json: {e}")
            
    username = os.environ.get('INSTAGRAM_USERNAME') or secrets.get('username')
    password = os.environ.get('INSTAGRAM_PASSWORD') or secrets.get('password')
    totp_secret = os.environ.get('INSTAGRAM_2FA_SECRET') or secrets.get('totp_secret')
    sync_url = os.environ.get('WEB_SERVICE_URL') or secrets.get('web_service_url')
    sync_token = os.environ.get('COOKIE_SYNC_TOKEN') or secrets.get('cookie_sync_token') or secrets.get('secret_key')

    if not username or not password:
        err_msg = "Error: INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD must be set in your system environment or secrets.json."
        print(err_msg)
        save_status("error", err_msg)
        sys.exit(1)

    print(f"Starting Instagram login automation for user: {username}...")

    try:
        with sync_playwright() as p:
            # Launch chromium in headless mode
            print("Launching headless browser...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Open Instagram login page
            print("Navigating to Instagram Login...")
            page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            
            # Wait for form inputs
            print("Waiting for username input field...")
            page.wait_for_selector('input[name="username"]', timeout=30000)

            # Fill inputs
            print("Typing credentials...")
            page.type('input[name="username"]', username, delay=100)
            page.type('input[name="password"]', password, delay=100)

            # Submit form
            print("Submitting login form...")
            page.click('button[type="submit"]')

            # Wait for response and check navigation/settlement
            page.wait_for_load_state("networkidle")
            time.sleep(5)

            current_url = page.url
            print(f"Current page URL: {current_url}")

            # Check if 2FA code is requested
            if "two_factor" in current_url or page.locator('input[name="oneTimePassword"]').is_visible():
                print("Two-Factor Authentication (2FA) is required.")
                if not totp_secret:
                    err_msg = "Error: 2FA required by Instagram, but INSTAGRAM_2FA_SECRET is not configured."
                    print(err_msg)
                    save_status("error", err_msg)
                    browser.close()
                    sys.exit(1)

                print("Generating TOTP code using 2FA secret...")
                totp = pyotp.TOTP(totp_secret.replace(" ", ""))
                code = totp.now()
                print(f"Generated 2FA Code: {code}")

                # Enter 2FA code
                page.wait_for_selector('input[name="oneTimePassword"]')
                page.type('input[name="oneTimePassword"]', code, delay=100)
                
                # Click Confirm
                confirm_btn = page.locator('button:has-text("Confirm")')
                if confirm_btn.is_visible():
                    confirm_btn.click()
                else:
                    page.click('button[type="button"]')

                page.wait_for_load_state("networkidle")
                time.sleep(5)
                print(f"URL after 2FA confirmation: {page.url}")

            # Check if sessionid cookie exists to confirm login
            cookies = context.cookies()
            session_cookie = [c for c in cookies if c['name'] == 'sessionid']

            if not session_cookie:
                err_msg = "sessionid cookie not found. Login failed or blocked."
                body_text = page.locator("body").inner_text()
                if "Suspicious Login Attempt" in body_text or "Verify It's You" in body_text:
                    err_msg = "Instagram flagged the login (Suspicious Login / Verify It's You)."
                print(f"Error: {err_msg}")
                status_data = save_status("error", err_msg)
                browser.close()
                sync_to_web_service(sync_url, sync_token, None, status_data)
                sys.exit(1)

            print("Login successful! Constructing Netscape cookie format...")

            # Format to Netscape Cookie File format
            netscape_lines = [
                "# Netscape HTTP Cookie File",
                "# This file was automatically generated by SnapStream",
                "# Do not edit this file directly.",
                ""
            ]

            for cookie in cookies:
                domain = cookie['domain']
                include_subdomains = "TRUE" if domain.startswith('.') else "FALSE"
                path = cookie['path']
                secure = "TRUE" if cookie['secure'] else "FALSE"
                expires = str(int(cookie.get('expires', 0))) if 'expires' in cookie else "0"
                name = cookie['name']
                value = cookie['value']

                line = f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}"
                netscape_lines.append(line)

            # Save to cookies.txt in the same directory
            output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(netscape_lines) + "\n")

            print(f"Success! Saved Netscape format cookies to: {output_path}")
            status_data = save_status("success")
            browser.close()
            sync_to_web_service(sync_url, sync_token, "\n".join(netscape_lines) + "\n", status_data)

    except Exception as e:
        err_msg = f"Fatal error: {e}"
        print(err_msg)
        status_data = save_status("error", err_msg)
        sync_to_web_service(sync_url, sync_token, None, status_data)
        sys.exit(1)

if __name__ == '__main__':
    main()
