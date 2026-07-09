import os
import threading
import urllib.request
import json
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, stream_with_context, send_from_directory, session, redirect, url_for
import yt_dlp

app = Flask(__name__, static_folder="static", template_folder="static")

# Admin Credentials and Secret Key Settings
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin_password_2026"
app.secret_key = "reelflow_secure_admin_session_key_2026"

try:
    if os.path.exists("secrets.json"):
        with open("secrets.json", "r", encoding="utf-8") as f:
            secrets_data = json.load(f)
            ADMIN_USERNAME = secrets_data.get("admin_username", ADMIN_USERNAME)
            ADMIN_PASSWORD = secrets_data.get("admin_password", ADMIN_PASSWORD)
            if "secret_key" in secrets_data:
                app.secret_key = secrets_data["secret_key"]
except Exception as e:
    print(f"Error loading admin credentials or secret key: {e}")

# Stats telemetry lock and file
stats_lock = threading.Lock()
STATS_FILE = "stats.json"

def parse_user_agent(ua_string):
    if not ua_string:
        return "Other", "Other"
        
    ua_lower = ua_string.lower()
    
    # Platform / OS
    if "windows" in ua_lower:
        platform = "Windows"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        if "iphone" in ua_lower or "ipad" in ua_lower or "ipod" in ua_lower:
            platform = "iOS"
        else:
            platform = "macOS"
    elif "android" in ua_lower:
        platform = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower or "ipod" in ua_lower:
        platform = "iOS"
    elif "linux" in ua_lower:
        platform = "Linux"
    else:
        platform = "Other"
        
    # Browser
    if "edg" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower and "safari" in ua_lower and "opr" not in ua_lower and "opt" not in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "opr" in ua_lower or "opera" in ua_lower:
        browser = "Opera"
    else:
        browser = "Other"
        
    return browser, platform

def track_visit(action_type):
    try:
        # Try to get visitor's IP and User-Agent
        ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1')
        if ',' in ip_addr:
            ip_addr = ip_addr.split(',')[0].strip()
            
        ua_str = request.headers.get('User-Agent', '')
        
        # Hash IP for privacy
        ip_hash = hashlib.sha256(ip_addr.encode('utf-8')).hexdigest()[:16]
        
        # Get current date
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Parse User-Agent
        browser, platform = parse_user_agent(ua_str)
        
        with stats_lock:
            stats = {
                "total_page_views": 0,
                "total_api_info": 0,
                "total_api_download": 0,
                "daily": {},
                "browsers": {},
                "platforms": {}
            }
            
            if os.path.exists(STATS_FILE):
                try:
                    with open(STATS_FILE, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        for k in stats.keys():
                            if k in loaded:
                                stats[k] = loaded[k]
                except Exception:
                    pass
                    
            # Update metrics
            if action_type == 'page_view':
                stats["total_page_views"] += 1
            elif action_type == 'api_info':
                stats["total_api_info"] += 1
            elif action_type == 'api_download':
                stats["total_api_download"] += 1
                
            # Ensure daily structure
            if date_str not in stats["daily"]:
                stats["daily"][date_str] = {
                    "page_views": 0,
                    "api_info": 0,
                    "api_download": 0,
                    "unique_visitors": []
                }
                
            day_stats = stats["daily"][date_str]
            
            if action_type == 'page_view':
                day_stats["page_views"] = day_stats.get("page_views", 0) + 1
            elif action_type == 'api_info':
                day_stats["api_info"] = day_stats.get("api_info", 0) + 1
            elif action_type == 'api_download':
                day_stats["api_download"] = day_stats.get("api_download", 0) + 1
                
            # Add to unique visitors if not already there
            if "unique_visitors" not in day_stats:
                day_stats["unique_visitors"] = []
            if ip_hash not in day_stats["unique_visitors"]:
                day_stats["unique_visitors"].append(ip_hash)
                
            # Update browser & platform charts (only on page views to avoid skewing)
            if action_type == 'page_view':
                stats["browsers"][browser] = stats["browsers"].get(browser, 0) + 1
                stats["platforms"][platform] = stats["platforms"].get(platform, 0) + 1
                
            try:
                with open(STATS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(stats, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"Error saving stats: {e}")
    except Exception as e:
        print(f"Error tracking visit: {e}")


# Persistent history lock and file
history_lock = threading.Lock()
HISTORY_FILE = "history.json"

def add_to_history(item):
    with history_lock:
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                history = []
        
        # Avoid duplicates in history
        history = [x for x in history if x.get('url') != item.get('url')]
        history.insert(0, item)
        history = history[:50]  # Limit to last 50 downloads
        
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving history: {e}")

def get_history():
    with history_lock:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

def apply_cookies_to_ytdl(ydl_opts, browser_cookies=None):
    cookies_path = os.path.join(os.getcwd(), "cookies.txt")
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 0:
        ydl_opts['cookiefile'] = cookies_path
        print("Using server-side cookies.txt configuration")
    elif browser_cookies and browser_cookies != 'none':
        ydl_opts['cookiesfrombrowser'] = (browser_cookies,)
        print(f"Using cookies from browser: {browser_cookies}")

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins}:{secs:02d}"

@app.route('/')
def index():
    track_visit('page_view')
    return render_template("index.html")

@app.route('/api/info', methods=['POST'])
def get_info():
    track_visit('api_info')
    data = request.json or {}
    url = data.get('url')
    browser_cookies = data.get('cookies')
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
        
    ydl_opts = {
        'skip_download': True,
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    apply_cookies_to_ytdl(ydl_opts, browser_cookies)
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                "title": info.get('title', 'Instagram Reel'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": format_duration(info.get('duration', 0)),
                "uploader": info.get('uploader', 'Unknown Creator'),
                "url": url,
                "video_url": info.get('url')  # Direct video stream URL on CDN
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download-stream')
def download_stream():
    track_visit('api_download')
    video_url = request.args.get('url')
    filename = request.args.get('filename', 'video.mp4')
    if not video_url:
        return "Missing url parameter", 400
        
    try:
        req = urllib.request.Request(
            video_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        )
        response = urllib.request.urlopen(req, timeout=20)
        
        def generate():
            while True:
                chunk = response.read(16384)  # Stream in 16KB chunks
                if not chunk:
                    break
                yield chunk
                
        # Format a safe filename
        safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in ' .-_']).strip()
        if not safe_filename.endswith('.mp4'):
            safe_filename += '.mp4'
            
        headers = {
            'Content-Disposition': f'attachment; filename="{safe_filename}"',
            'Content-Type': 'video/mp4'
        }
        return Response(stream_with_context(generate()), headers=headers)
    except Exception as e:
        return f"Error streaming video: {e}", 500

@app.route('/api/history')
def get_history_api():
    return jsonify(get_history())

@app.route('/api/history/add', methods=['POST'])
def add_history_item():
    data = request.json or {}
    add_to_history({
        "title": data.get('title', 'Instagram Reel'),
        "thumbnail": data.get('thumbnail', ''),
        "duration": data.get('duration', 'Unknown'),
        "uploader": data.get('uploader', 'Unknown Creator'),
        "url": data.get('url'),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    return jsonify({"success": True})

@app.route('/api/proxy-image')
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing url parameter", 400
    try:
        req = urllib.request.Request(
            img_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            img_data = response.read()
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            return img_data, 200, {'Content-Type': content_type}
    except Exception as e:
        return f"Error proxying image: {e}", 500

@app.route('/robots.txt')
def robots():
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(app.static_folder, 'sitemap.xml')

# --- Admin Panel & Telemetry APIs ---
@app.route('/admin')
def admin_panel():
    logged_in = session.get('admin_logged_in', False)
    return render_template("admin.html", logged_in=logged_in)

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_panel'))

@app.route('/admin/api/stats')
def admin_get_stats():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    stats_data = {
        "total_page_views": 0,
        "total_api_info": 0,
        "total_api_download": 0,
        "daily": {},
        "browsers": {},
        "platforms": {}
    }
    
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                stats_data = json.load(f)
        except Exception:
            pass
            
    # Include history for the admin panel log table
    history_data = get_history()
    
    # Include cookie rotation status
    cookie_status = None
    status_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookie_status.json')
    if os.path.exists(status_path):
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                cookie_status = json.load(f)
        except Exception:
            pass
            
    return jsonify({
        "stats": stats_data,
        "history": history_data,
        "cookie_status": cookie_status
    })

@app.route('/admin/api/history/delete', methods=['POST'])
def admin_delete_history():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json or {}
    target_url = data.get('url')
    if not target_url:
        return jsonify({"error": "No URL provided"}), 400
        
    with history_lock:
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass
                
        # Filter out the target item
        new_history = [x for x in history if x.get('url') != target_url]
        
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_history, f, indent=4, ensure_ascii=False)
        except Exception as e:
            return jsonify({"error": f"Failed to save updated history: {e}"}), 500
            
    return jsonify({"success": True})

@app.route('/admin/api/reset-stats', methods=['POST'])
def admin_reset_stats():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    empty_stats = {
        "total_page_views": 0,
        "total_api_info": 0,
        "total_api_download": 0,
        "daily": {},
        "browsers": {},
        "platforms": {}
    }
    
    with stats_lock:
        try:
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(empty_stats, f, indent=4, ensure_ascii=False)
        except Exception as e:
            return jsonify({"error": f"Failed to reset stats: {e}"}), 500
            
    return jsonify({"success": True})

@app.route('/api/cookies/sync', methods=['POST'])
def sync_cookies():
    token = request.headers.get('Authorization')
    expected_token = os.environ.get('COOKIE_SYNC_TOKEN')
    if not expected_token and os.path.exists("secrets.json"):
        try:
            with open("secrets.json", "r", encoding="utf-8") as f:
                expected_token = json.load(f).get("secret_key")
        except:
            pass
            
    if not expected_token or token != f"Bearer {expected_token}":
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json or {}
    cookies_content = data.get('cookies_content')
    status_content = data.get('status_content')
    
    if not cookies_content and not status_content:
        return jsonify({"error": "Missing content to sync"}), 400
        
    try:
        if cookies_content:
            with open('cookies.txt', 'w', encoding='utf-8') as f:
                f.write(cookies_content)
        if status_content:
            with open('cookie_status.json', 'w', encoding='utf-8') as f:
                json.dump(status_content, f, indent=4, ensure_ascii=False)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
