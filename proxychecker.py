import aiohttp
import asyncio
import time
import urllib.parse
from typing import List, Tuple
from telegram import Update, InputFile
from telegram.ext import ContextTypes

CHECK_URLS = [
    "http://ip-api.com/json",
    "http://api.ipify.org",
    "http://httpbin.org/ip",
]
TIMEOUT = 20

def format_proxy_url(proxy: str) -> str:
    proxy = proxy.strip()
    if not proxy:
        return None
    
    # If it's already a full URL, handle it properly
    if proxy.startswith('http://') or proxy.startswith('https://'):
        try:
            parsed = urllib.parse.urlparse(proxy)
            if parsed.username or parsed.password:
                # URL encode the username and password components
                username = urllib.parse.quote(parsed.username or '', safe='')
                password = urllib.parse.quote(parsed.password or '', safe='')
                # Reconstruct the URL with encoded credentials
                netloc = f"{username}:{password}@{parsed.hostname}:{parsed.port}"
                return urllib.parse.urlunparse((
                    parsed.scheme,
                    netloc,
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                    ''
                ))
            return proxy
        except:
            return proxy
    
    # Handle the old format: host:port:user:pass
    parts = proxy.split(':')
    if len(parts) == 4:
        # URL encode username and password to handle special characters
        username = urllib.parse.quote(parts[2], safe='')
        password = urllib.parse.quote(parts[3], safe='')
        return f"http://{username}:{password}@{parts[0]}:{parts[1]}"
    elif len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    else:
        return proxy

async def check_single_proxy(proxy: str) -> Tuple[str, bool, float]:
    start_time = time.time()
    try:
        proxy_url = format_proxy_url(proxy)
        if not proxy_url:
            return proxy, False, 0
        
        # Debug: print the formatted proxy URL
        # print(f"Checking proxy: {proxy} -> {proxy_url}")
        
        connector = aiohttp.TCPConnector(ssl=False, force_close=True, enable_cleanup_closed=True)
        timeout = aiohttp.ClientTimeout(total=TIMEOUT, connect=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            for check_url in CHECK_URLS:
                try:
                    async with session.get(
                        check_url,
                        proxy=proxy_url,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Accept': '*/*',
                            'Connection': 'keep-alive'
                        }
                    ) as response:
                        if response.status == 200:
                            elapsed = time.time() - start_time
                            return proxy, True, elapsed
                except asyncio.TimeoutError:
                    continue
                except aiohttp.ClientProxyConnectionError:
                    continue
                except aiohttp.ClientError as e:
                    continue
                except Exception:
                    continue
        return proxy, False, 0
    except Exception as e:
        # Debug: print the error
        # print(f"Error checking proxy {proxy}: {e}")
        return proxy, False, 0

async def check_proxies_batch(proxies: List[str], max_concurrent: int = 50) -> Tuple[List[str], List[str]]:
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def check_with_semaphore(proxy):
        async with semaphore:
            return await check_single_proxy(proxy)
    
    tasks = [check_with_semaphore(p) for p in proxies if p.strip()]
    results = await asyncio.gather(*tasks)
    
    live = []
    dead = []
    for proxy, is_live, response_time in results:
        if is_live:
            live.append((proxy, response_time))
        else:
            dead.append(proxy)
    
    return live, dead

class ProxyChecker:
    def __init__(self):
        self.proxies_file = "proxies.txt"
    
    def load_proxies(self) -> List[str]:
        try:
            with open(self.proxies_file, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except:
            return []
    
    def save_proxies(self, proxies: List[str]):
        with open(self.proxies_file, 'w') as f:
            f.write('\n'.join(proxies))

    async def chkproxy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔍 𝙲𝙷𝙴𝙲𝙺 𝙿𝚁𝙾𝚇𝚈\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ /chkproxy ip:port:user:pass\n"
                "𝗠𝘂𝗹𝘁𝗶 ⌁ /chkproxy proxy1 proxy2 proxy3\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        proxies = context.args
        status = await update.message.reply_text(f"🔍 𝙲𝚑𝚎𝚌𝚔𝚒𝚗𝚐 {len(proxies)} 𝚙𝚛𝚘𝚡𝚒𝚎𝚜...")
        
        start_time = time.time()
        live, dead = await check_proxies_batch(proxies)
        elapsed = time.time() - start_time
        
        result_msg = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔍 𝙿𝚁𝙾𝚇𝚈 𝙲𝙷𝙴𝙲𝙺 𝚁𝙴𝚂𝚄𝙻𝚃\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        if live:
            result_msg += "✅ 𝗟𝗶𝘃𝗲 𝗣𝗿𝗼𝘅𝗶𝗲𝘀:\n"
            for proxy, resp_time in live:
                result_msg += f"  ⌁ {proxy} ({resp_time:.2f}s)\n"
            result_msg += "\n"
        
        if dead:
            result_msg += "❌ 𝗗𝗲𝗮𝗱 𝗣𝗿𝗼𝘅𝗶𝗲𝘀:\n"
            for proxy in dead[:10]:
                result_msg += f"  ⌁ {proxy}\n"
            if len(dead) > 10:
                result_msg += f"  ... 𝚊𝚗𝚍 {len(dead)-10} 𝚖𝚘𝚛𝚎\n"
            result_msg += "\n"
        
        result_msg += (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝗟𝗶𝘃𝗲 ⌁ {len(live)} | 𝗗𝗲𝗮𝗱 ⌁ {len(dead)}\n"
            f"𝗧𝗶𝗺𝗲 ⌁ {elapsed:.2f}s\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        
        await status.edit_text(result_msg)

    async def clp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        proxies = self.load_proxies()
        
        if not proxies:
            await update.message.reply_text("❌ 𝙽𝚘 𝚙𝚛𝚘𝚡𝚒𝚎𝚜 𝚕𝚘𝚊𝚍𝚎𝚍 𝚒𝚗 𝚋𝚘𝚝!")
            return
        
        status = await update.message.reply_text(f"🔍 𝙲𝚑𝚎𝚌𝚔𝚒𝚗𝚐 {len(proxies)} 𝚕𝚘𝚊𝚍𝚎𝚍 𝚙𝚛𝚘𝚡𝚒𝚎𝚜...")
        
        start_time = time.time()
        live, dead = await check_proxies_batch(proxies)
        elapsed = time.time() - start_time
        
        live_proxies = [p for p, _ in live]
        self.save_proxies(live_proxies)
        
        result_msg = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔄 𝙿𝚁𝙾𝚇𝚈 𝙲𝙻𝙴𝙰𝙽𝚄𝙿 𝙲𝙾𝙼𝙿𝙻𝙴𝚃𝙴\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"𝗧𝗼𝘁𝗮𝗹 ⌁ {len(proxies)} 𝚙𝚛𝚘𝚡𝚒𝚎𝚜\n"
            f"𝗟𝗶𝘃𝗲 ⌁ {len(live)} ✅\n"
            f"𝗗𝗲𝗮𝗱 ⌁ {len(dead)} ❌ (𝚛𝚎𝚖𝚘𝚟𝚎𝚍)\n"
            f"𝗧𝗶𝗺𝗲 ⌁ {elapsed:.2f}s\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ 𝙵𝚒𝚕𝚎 𝚞𝚙𝚍𝚊𝚝𝚎𝚍 𝚠𝚒𝚝𝚑 {len(live)} 𝚙𝚛𝚘𝚡𝚒𝚎𝚜\n"
            "📌 𝚄𝚜𝚎 /reloadproxies 𝚝𝚘 𝚛𝚎𝚕𝚘𝚊𝚍 𝚐𝚊𝚝𝚎𝚜\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        
        await status.edit_text(result_msg)

    async def ptxt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📄 𝙲𝙷𝙴𝙲𝙺 𝙿𝚁𝙾𝚇𝚈 𝙵𝙸𝙻𝙴\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ 𝚁𝚎𝚙𝚕𝚢 𝚝𝚘 𝚙𝚛𝚘𝚡𝚢 𝚏𝚒𝚕𝚎 𝚠𝚒𝚝𝚑 /ptxt\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        try:
            doc = update.message.reply_to_message.document
            file = await doc.get_file()
            content = await file.download_as_bytearray()
            proxies = content.decode('utf-8', errors='ignore').strip().splitlines()
            proxies = [p.strip() for p in proxies if p.strip()]
            
            if not proxies:
                await update.message.reply_text("❌ 𝙽𝚘 𝚙𝚛𝚘𝚡𝚒𝚎𝚜 𝚏𝚘𝚞𝚗𝚍 𝚒𝚗 𝚏𝚒𝚕𝚎!")
                return
            
            status = await update.message.reply_text(f"🔍 𝙲𝚑𝚎𝚌𝚔𝚒𝚗𝚐 {len(proxies)} 𝚙𝚛𝚘𝚡𝚒𝚎𝚜...")
            
            start_time = time.time()
            live, dead = await check_proxies_batch(proxies)
            elapsed = time.time() - start_time
            
            if live:
                live_proxies = [p for p, _ in live]
                filename = f"live_proxies_{int(time.time())}.txt"
                with open(filename, 'w') as f:
                    f.write('\n'.join(live_proxies))
                
                with open(filename, 'rb') as f:
                    await update.message.reply_document(
                        document=InputFile(f, filename=filename),
                        caption=(
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"✅ 𝙻𝙸𝚅𝙴 𝙿𝚁𝙾𝚇𝙸𝙴𝚂\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"𝗧𝗼𝘁𝗮𝗹 ⌁ {len(proxies)}\n"
                            f"𝗟𝗶𝘃𝗲 ⌁ {len(live)} ✅\n"
                            f"𝗗𝗲𝗮𝗱 ⌁ {len(dead)} ❌\n"
                            f"𝗧𝗶𝗺𝗲 ⌁ {elapsed:.2f}s\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━"
                        )
                    )
                
                import os
                os.remove(filename)
                await status.delete()
            else:
                await status.edit_text(
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "❌ 𝙰𝙻𝙻 𝙿𝚁𝙾𝚇𝙸𝙴𝚂 𝙳𝙴𝙰𝙳\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"𝗧𝗼𝘁𝗮𝗹 ⌁ {len(proxies)}\n"
                    f"𝗟𝗶𝘃𝗲 ⌁ 0\n"
                    f"𝗗𝗲𝗮𝗱 ⌁ {len(dead)}\n"
                    f"𝗧𝗶𝗺𝗲 ⌁ {elapsed:.2f}s\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━"
                )
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

proxy_checker = ProxyChecker()
