import re
import os
import json
import time
import asyncio
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple
import itertools
from functools import lru_cache

MAX_WORKERS = 32
CHUNK_SIZE = 1024 * 1024 * 20
BUFFER_SIZE = 1024 * 1024 * 32
MAX_BATCH_SIZE = 1000000

EMAIL_PASS_PATTERN = re.compile(
    b'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+):([^:\\s\\r\\n]+)', 
    re.MULTILINE | re.DOTALL | re.ASCII
)

CARD_PATTERN = re.compile(
    b'''(?:^|[^0-9])([45][0-9]{15}|4[0-9]{12}(?:[0-9]{3})?|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})[^0-9]*?([0-9]{2})[^0-9]*?([0-9]{2,4})[^0-9]*?([0-9]{3,4})''',
    re.MULTILINE | re.DOTALL | re.ASCII
)

ULP_PATTERN = re.compile(
    b'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+):([^:\\s\\r\\n]+)', 
    re.MULTILINE | re.DOTALL | re.ASCII
)

@lru_cache(maxsize=4096)
def cached_decode(byte_string):
    return byte_string.decode('ascii', errors='ignore')

def process_chunk(chunk: bytes) -> List[Tuple[str, str]]:
    try:
        matches = EMAIL_PASS_PATTERN.finditer(chunk)
        return [(cached_decode(m.group(1)), cached_decode(m.group(2))) for m in matches]
    except:
        return []

def process_card_chunk(chunk: bytes) -> List[Tuple[str, str, str, str]]:
    try:
        results = []
        matches = CARD_PATTERN.finditer(chunk)
        
        for m in matches:
            card = cached_decode(m.group(1))
            if not card or len(card) < 15:
                continue
            
            s1 = sum(int(d) for d in card[-1::-2])
            s2 = sum(sum(divmod(int(d)*2,10)) for d in card[-2::-2])
            if (s1 + s2) % 10 != 0:
                continue
                
            month = cached_decode(m.group(2))
            year = cached_decode(m.group(3))
            cvv = cached_decode(m.group(4))
            
            if not (1 <= int(month) <= 12):
                continue
                
            year = year[-2:] if len(year) == 4 else year
            results.append((card, month, year, cvv))
            
        return results
    except:
        return []

def process_ulp_chunk(chunk: bytes) -> List[Tuple[str, str]]:
    try:
        matches = ULP_PATTERN.finditer(chunk)
        return [(cached_decode(m.group(1)), cached_decode(m.group(2))) for m in matches]
    except:
        return []

async def update_progress(message, start_time):
    try:
        while True:
            elapsed = time.time() - start_time
            await message.edit_text(f"⚡ 𝙿𝚛𝚘𝚌𝚎𝚜𝚜𝚒𝚗𝚐...\n𝗧𝗶𝗺𝗲 ⌁ {elapsed:.1f}s")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except:
        pass

async def extract_combos(content: bytes) -> List[Tuple[str, str]]:
    chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        chunk_results = await loop.run_in_executor(
            None,
            lambda: list(itertools.chain.from_iterable(
                executor.map(process_chunk, chunks, chunksize=max(1, len(chunks)//MAX_WORKERS))
            ))
        )
    seen = set()
    return [combo for combo in chunk_results if combo[0] not in seen and not seen.add(combo[0])]

async def extract_cards(content: bytes) -> List[Tuple[str, str, str, str]]:
    chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        card_results = await loop.run_in_executor(
            None,
            lambda: list(itertools.chain.from_iterable(
                executor.map(process_card_chunk, chunks, chunksize=max(1, len(chunks)//MAX_WORKERS))
            ))
        )
    seen = set()
    return [card for card in card_results if card[0] not in seen and not seen.add(card[0])]

async def extract_ulp(content: bytes) -> List[Tuple[str, str]]:
    chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        chunk_results = await loop.run_in_executor(
            None,
            lambda: list(itertools.chain.from_iterable(
                executor.map(process_ulp_chunk, chunks, chunksize=max(1, len(chunks)//MAX_WORKERS))
            ))
        )
    seen = set()
    return [combo for combo in chunk_results if combo[0] not in seen and not seen.add(combo[0])]

async def save_combos(combos: List[Tuple[str, str]], filename: str):
    with open(filename, 'wb', buffering=BUFFER_SIZE) as f:
        batch_size = 10000
        for i in range(0, len(combos), batch_size):
            batch = combos[i:i + batch_size]
            f.write(b''.join(f"{email}:{password}\n".encode('utf-8') for email, password in batch))

async def save_cards(cards: List[Tuple[str, str, str, str]], filename: str):
    with open(filename, 'wb', buffering=BUFFER_SIZE) as f:
        batch_size = 10000
        for i in range(0, len(cards), batch_size):
            batch = cards[i:i + batch_size]
            f.write(b''.join(f"{card}|{month}|{year}|{cvv}\n".encode('utf-8') for card, month, year, cvv in batch))

async def save_ulp(ulp_pairs: List[Tuple[str, str]], filename: str):
    with open(filename, 'w', buffering=BUFFER_SIZE) as f:
        batch_size = 10000
        for i in range(0, len(ulp_pairs), batch_size):
            batch = ulp_pairs[i:i + batch_size]
            f.write(''.join(f"{email}:{password}\n" for email, password in batch))

class CleanerTools:
    def __init__(self):
        self.stats_file = "cleaner_stats.json"
    
    def load_stats(self):
        try:
            with open(self.stats_file, "r") as f:
                return json.load(f)
        except:
            return {"combos_cleaned": 0, "cards_cleaned": 0, "ulp_cleaned": 0}
    
    def save_stats(self, stats):
        with open(self.stats_file, "w") as f:
            json.dump(stats, f)

    async def clean_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🗂️ 𝙲𝙻𝙴𝙰𝙽 𝙲𝙾𝙼𝙱𝙾𝚂\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ Reply to a file with /clean\n"
                "𝗙𝗼𝗿𝗺𝗮𝘁 ⌁ email:password\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        try:
            start_time = time.time()
            status = await update.message.reply_text("⚡ 𝙿𝚛𝚘𝚌𝚎𝚜𝚜𝚒𝚗𝚐...")
            
            doc = update.message.reply_to_message.document
            file = await doc.get_file()
            content = await file.download_as_bytearray()
            
            progress_task = asyncio.create_task(update_progress(status, start_time))
            combos = await extract_combos(content)
            total_combos = len(combos)
            progress_task.cancel()
            
            if not total_combos:
                await status.edit_text("❌ No combos found!")
                return
            
            filename = f"cleaned_{int(time.time())}.txt"
            await save_combos(combos, filename)
            
            elapsed_time = time.time() - start_time
            speed = total_combos / elapsed_time if elapsed_time > 0 else 0
            
            with open(filename, "rb") as f:
                await update.message.reply_document(
                    document=InputFile(f, filename=filename),
                    caption=(
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ 𝙲𝙻𝙴𝙰𝙽𝙸𝙽𝙶 𝙲𝙾𝙼𝙿𝙻𝙴𝚃𝙴\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"𝗧𝗼𝘁𝗮𝗹 ⌁ {total_combos:,} lines\n"
                        f"𝗧𝗶𝗺𝗲 ⌁ {elapsed_time:.2f}s\n"
                        f"𝗦𝗽𝗲𝗲𝗱 ⌁ {speed:.0f}/sec\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━"
                    )
                )
            os.remove(filename)
            await status.delete()
            
            stats = self.load_stats()
            stats["combos_cleaned"] += total_combos
            self.save_stats(stats)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def cards_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "💳 𝙲𝙻𝙴𝙰𝙽 𝙲𝙰𝚁𝙳𝚂\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ Reply to a file with /ccn\n"
                "𝗙𝗼𝗿𝗺𝗮𝘁 ⌁ Extracts valid CC from any format\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        try:
            start_time = time.time()
            status = await update.message.reply_text("⚡ 𝙿𝚛𝚘𝚌𝚎𝚜𝚜𝚒𝚗𝚐...")
            
            doc = update.message.reply_to_message.document
            file = await doc.get_file()
            content = await file.download_as_bytearray()
            
            progress_task = asyncio.create_task(update_progress(status, start_time))
            cards = await extract_cards(content)
            total_cards = len(cards)
            progress_task.cancel()
            
            if not total_cards:
                await status.edit_text("❌ No valid cards found!")
                return
            
            filename = f"cards_{int(time.time())}.txt"
            await save_cards(cards, filename)
            
            elapsed_time = time.time() - start_time
            speed = total_cards / elapsed_time if elapsed_time > 0 else 0
            
            with open(filename, "rb") as f:
                await update.message.reply_document(
                    document=InputFile(f, filename=filename),
                    caption=(
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ 𝙲𝙰𝚁𝙳𝚂 𝙴𝚇𝚃𝚁𝙰𝙲𝚃𝙴𝙳\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"𝗧𝗼𝘁𝗮𝗹 ⌁ {total_cards:,} cards\n"
                        f"𝗧𝗶𝗺𝗲 ⌁ {elapsed_time:.2f}s\n"
                        f"𝗦𝗽𝗲𝗲𝗱 ⌁ {speed:.0f}/sec\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━"
                    )
                )
            os.remove(filename)
            await status.delete()
            
            stats = self.load_stats()
            stats["cards_cleaned"] += total_cards
            self.save_stats(stats)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def ulp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📧 𝙴𝚇𝚃𝚁𝙰𝙲𝚃 𝚄𝙻𝙿\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ Reply to a file with /ulp\n"
                "𝗙𝗼𝗿𝗺𝗮𝘁 ⌁ Extracts email:password\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        try:
            start_time = time.time()
            status = await update.message.reply_text("⚡ 𝙿𝚛𝚘𝚌𝚎𝚜𝚜𝚒𝚗𝚐...")
            
            doc = update.message.reply_to_message.document
            file = await doc.get_file()
            content = await file.download_as_bytearray()
            
            progress_task = asyncio.create_task(update_progress(status, start_time))
            ulp_pairs = await extract_ulp(content)
            total_pairs = len(ulp_pairs)
            progress_task.cancel()
            
            if not total_pairs:
                await status.edit_text("❌ No valid email:password pairs found!")
                return
            
            filename = f"ulp_{int(time.time())}.txt"
            await save_ulp(ulp_pairs, filename)
            
            elapsed_time = time.time() - start_time
            speed = total_pairs / elapsed_time if elapsed_time > 0 else 0
            
            with open(filename, "rb") as f:
                await update.message.reply_document(
                    document=InputFile(f, filename=filename),
                    caption=(
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ 𝚄𝙻𝙿 𝙴𝚇𝚃𝚁𝙰𝙲𝚃𝙴𝙳\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"𝗧𝗼𝘁𝗮𝗹 ⌁ {total_pairs:,} pairs\n"
                        f"𝗧𝗶𝗺𝗲 ⌁ {elapsed_time:.2f}s\n"
                        f"𝗦𝗽𝗲𝗲𝗱 ⌁ {speed:.0f}/sec\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━"
                    )
                )
            os.remove(filename)
            await status.delete()
            
            stats = self.load_stats()
            stats["ulp_cleaned"] += total_pairs
            self.save_stats(stats)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def txt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧾 𝙲𝙾𝙽𝚅𝙴𝚁𝚃 𝚃𝙾 𝚃𝚇𝚃\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ Reply to text/file with /txt\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        try:
            replied = update.message.reply_to_message
            content = ""
            
            if replied.document:
                file = await replied.document.get_file()
                content_bytes = await file.download_as_bytearray()
                content = content_bytes.decode('utf-8', errors='ignore')
            elif replied.text:
                content = replied.text
            else:
                await update.message.reply_text("❌ No text content found!")
                return
            
            filename = f"converted_{int(time.time())}.txt"
            with open(filename, 'w') as f:
                f.write(content)
            
            with open(filename, "rb") as f:
                await update.message.reply_document(
                    document=InputFile(f, filename=filename),
                    caption=f"✅ 𝙲𝚘𝚗𝚟𝚎𝚛𝚝𝚎𝚍 𝚝𝚘 .𝚝𝚡𝚝 ({len(content):,} chars)"
                )
            os.remove(filename)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def split_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🪚 𝚂𝙿𝙻𝙸𝚃 𝙵𝙸𝙻𝙴\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ /split <lines_per_file>\n"
                "𝗘𝘅𝗮𝗺𝗽𝗹𝗲 ⌁ /split 10000\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        try:
            lines_per_file = int(context.args[0]) if context.args else 10000
            
            doc = update.message.reply_to_message.document
            file = await doc.get_file()
            content = await file.download_as_bytearray()
            lines = content.decode('utf-8', errors='ignore').splitlines()
            
            total_lines = len(lines)
            num_files = (total_lines + lines_per_file - 1) // lines_per_file
            
            status = await update.message.reply_text(f"⚡ 𝚂𝚙𝚕𝚒𝚝𝚝𝚒𝚗𝚐 𝚒𝚗𝚝𝚘 {num_files} 𝚏𝚒𝚕𝚎𝚜...")
            
            for i in range(0, total_lines, lines_per_file):
                batch = lines[i:i + lines_per_file]
                batch_num = i // lines_per_file + 1
                filename = f"split_{batch_num}.txt"
                
                with open(filename, 'w') as f:
                    f.write('\n'.join(batch))
                
                with open(filename, "rb") as f:
                    await update.message.reply_document(
                        document=InputFile(f, filename=filename),
                        caption=f"📄 𝙿𝚊𝚛𝚝 {batch_num}/{num_files} | {len(batch):,} 𝚕𝚒𝚗𝚎𝚜"
                    )
                os.remove(filename)
            
            await status.edit_text(f"✅ 𝚂𝚙𝚕𝚒𝚝 𝚌𝚘𝚖𝚙𝚕𝚎𝚝𝚎! {total_lines:,} 𝚕𝚒𝚗𝚎𝚜 → {num_files} 𝚏𝚒𝚕𝚎𝚜")
            
        except ValueError:
            await update.message.reply_text("❌ Invalid number! Use: /split 10000")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def bin_filter_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔍 𝙵𝙸𝙻𝚃𝙴𝚁 𝙱𝚈 𝙱𝙸𝙽\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ /bin <bin_prefix>\n"
                "𝗘𝘅𝗮𝗺𝗽𝗹𝗲 ⌁ /bin 424242\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        if not context.args:
            await update.message.reply_text("❌ Please provide a BIN! Example: /bin 424242")
            return

        try:
            bin_prefix = context.args[0]
            
            doc = update.message.reply_to_message.document
            file = await doc.get_file()
            content = await file.download_as_bytearray()
            lines = content.decode('utf-8', errors='ignore').splitlines()
            
            filtered = [line for line in lines if line.startswith(bin_prefix)]
            
            if not filtered:
                await update.message.reply_text(f"❌ No cards found with BIN: {bin_prefix}")
                return
            
            filename = f"bin_{bin_prefix}_{int(time.time())}.txt"
            with open(filename, 'w') as f:
                f.write('\n'.join(filtered))
            
            with open(filename, "rb") as f:
                await update.message.reply_document(
                    document=InputFile(f, filename=filename),
                    caption=(
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ 𝙱𝙸𝙽 𝙵𝙸𝙻𝚃𝙴𝚁𝙴𝙳\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"𝗕𝗜𝗡 ⌁ {bin_prefix}\n"
                        f"𝗙𝗼𝘂𝗻𝗱 ⌁ {len(filtered):,} cards\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━"
                    )
                )
            os.remove(filename)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def sort_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🗃️ 𝚂𝙾𝚁𝚃 𝙲𝙰𝚁𝙳𝚂\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ Reply to card file with /sort\n"
                "𝗦𝗼𝗿𝘁𝘀 ⌁ Visa, Mastercard, Amex, Discover\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        try:
            doc = update.message.reply_to_message.document
            file = await doc.get_file()
            content = await file.download_as_bytearray()
            lines = content.decode('utf-8', errors='ignore').splitlines()
            
            visa = []
            mastercard = []
            amex = []
            discover = []
            other = []
            
            for line in lines:
                card = line.split('|')[0] if '|' in line else line.split(':')[0] if ':' in line else line
                card = ''.join(filter(str.isdigit, card))
                
                if card.startswith('4'):
                    visa.append(line)
                elif card.startswith(('51', '52', '53', '54', '55')) or (card.startswith('2') and len(card) >= 2 and 2221 <= int(card[:4]) <= 2720):
                    mastercard.append(line)
                elif card.startswith(('34', '37')):
                    amex.append(line)
                elif card.startswith(('6011', '65', '644', '645', '646', '647', '648', '649')):
                    discover.append(line)
                else:
                    other.append(line)
            
            results = []
            for name, cards in [("Visa", visa), ("Mastercard", mastercard), ("Amex", amex), ("Discover", discover), ("Other", other)]:
                if cards:
                    filename = f"{name.lower()}_{int(time.time())}.txt"
                    with open(filename, 'w') as f:
                        f.write('\n'.join(cards))
                    
                    with open(filename, "rb") as f:
                        await update.message.reply_document(
                            document=InputFile(f, filename=filename),
                            caption=f"💳 {name} | {len(cards):,} cards"
                        )
                    os.remove(filename)
                    results.append(f"{name}: {len(cards):,}")
            
            await update.message.reply_text(
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ 𝚂𝙾𝚁𝚃𝙸𝙽𝙶 𝙲𝙾𝙼𝙿𝙻𝙴𝚃𝙴\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n" +
                "\n".join([f"𝗧𝗼𝘁𝗮𝗹 ⌁ {r}" for r in results]) +
                f"\n\n━━━━━━━━━━━━━━━━━━━━━━"
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

cleaner_tools = CleanerTools()
