# main.py (updated with fixed /stop command)
import asyncio
import re
import random
import string
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from colorama import Fore, init
from pymongo import MongoClient
from dateutil.relativedelta import relativedelta
import dateutil.parser

# Import the StripeProcessor from gate.py
from gate import StripeProcessor
from gate2 import StripeChargeProcessor
from gate3 import RazorpayProcessor
from gate4 import shopify_processor, check_card_shopify, check_site_shopify, check_all_sites_shopify, add_site, remove_site, get_sites, add_sites_from_file, format_charged_message as g4_format_charged, format_declined_message as g4_format_declined, format_approved_message as g4_format_approved
import gate5
from cleaner import cleaner_tools
from proxychecker import proxy_checker

# Initialize colorama and logging
init()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def to_monospace(text):
    """Convert text to monospace Unicode characters"""
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

class AdvancedCardChecker:
    def __init__(self):
        mongo_uri = os.environ.get('MONGODB_URI', 'mongodb+srv://ElectraOp:BGMI272@cluster0.1jmwb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client['stripe_checker']
        self.users_col = self.db['users']
        self.keys_col = self.db['keys']
        self.admin_id = 1612918900
        self.admin_ids = [1612918900]  # List of all admin IDs
        self.admin_username = "trial9pm"
        self.bot_username = None
        self.active_tasks = {}
        self.user_stats = {}
        self.user_semaphores = {}  # Per-user semaphore dictionary
        self.max_concurrent_per_user = 5  # Max concurrent requests per user (5 cards at once with different proxies)
        self.user_files = {}  # Store user's uploaded files
        self.stop_flags = {}  # Add stop flags for each user
        
        # Initialize Stripe Processor
        self.stripe_processor = StripeProcessor()
        self.stripe_processor.load_proxies()
        
        # Initialize Gate2 Stripe Charge Processor
        self.gate2_processor = StripeChargeProcessor()
        self.gate2_stats = {}
        self.gate2_stop_flags = {}
        self.gate2_active_tasks = {}
        self.gate2_status_messages = {}
        
        # Gate1 status messages for inline buttons
        self.gate1_status_messages = {}
        
        # Initialize Gate3 Razorpay Processor
        self.gate3_processor = RazorpayProcessor()
        self.gate3_stats = {}
        self.gate3_stop_flags = {}
        self.gate3_active_tasks = {}
        self.gate3_status_messages = {}
        self.gate3_last_completion = {}
        self.gate3_max_cards = 10
        self.gate3_cooldown_seconds = 50
        
        # Initialize Gate4 Shopify Processor
        self.gate4_stats = {}
        self.gate4_stop_flags = {}
        self.gate4_active_tasks = {}
        self.gate4_status_messages = {}
        self.gate4_max_cards = 1000
        self.gate4_user_site_choice = {}  # Tracks if user wants their own sites
        

    def create_banner(self):
        """Create a dynamic banner with system information."""
        return f"""
{Fore.CYAN}
╔══════════════════════════════════════════════════════════════╗
║ 🔥 Cc CHECKER BOT                                            ║
╠══════════════════════════════════════════════════════════════╣
║ ➤ Admin ID: {self.admin_id:<15}                             ║
║ ➤ Bot Username: @{self.bot_username or 'Initializing...':<20}║
║ ➤ Admin Contact: https://t.me/{self.admin_username:<15}      ║
╚══════════════════════════════════════════════════════════════╝
{Fore.YELLOW}
✅ System Ready
{Fore.RESET}
"""

    async def post_init(self, application: Application):
        """Initialize bot properties after startup"""
        self.bot_username = application.bot.username
        print(self.create_banner())

    def get_user_semaphore(self, user_id):
        """Get or create a semaphore for a specific user"""
        if user_id not in self.user_semaphores:
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_concurrent_per_user)
        return self.user_semaphores[user_id]

    def cleanup_user_semaphore(self, user_id):
        """Clean up semaphore when user is done"""
        if user_id in self.user_semaphores:
            del self.user_semaphores[user_id]

    async def is_user_allowed(self, user_id):
        """Check if user has active subscription"""
        user = self.users_col.find_one({'user_id': str(user_id)})
        if user and user.get('expires_at', datetime.now()) > datetime.now():
            return True
        return user_id == self.admin_id

    async def check_subscription(self, func):
        """Decorator to check user subscription status"""
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            if not await self.is_user_allowed(user_id):
                await update.message.reply_text(
                    "⛔ Subscription expired or invalid!\n"
                    f"Purchase a key with /redeem <key> or contact admin: https://t.me/{self.admin_username}"
                )
                return
            return await func(update, context)
        return wrapper

    async def send_admin_notification(self, user):
        keyboard = [
            [InlineKeyboardButton(f"✅ Allow {user.id}", callback_data=f'allow_{user.id}'),
             InlineKeyboardButton(f"❌ Deny {user.id}", callback_data=f'deny_{user.id}')]]
        message = (
            f"⚠️ New User Request:\n\n"
            f"👤 Name: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📧 Username: @{user.username if user.username else 'N/A'}\n\n"
            f"Click buttons below to approve/reject:"
        )
        try:
            await self.application.bot.send_message(
                chat_id=self.admin_id,
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")

    def is_admin(self, user_id):
        """Check if user is an admin"""
        return user_id in self.admin_ids or user_id == self.admin_id

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        keyboard = [
            [InlineKeyboardButton("⚔️ 𝗚𝗔𝗧𝗘𝗦", callback_data='gates'),
             InlineKeyboardButton("🛠️ 𝗧𝗢𝗢𝗟𝗦", callback_data='tools')],
            [InlineKeyboardButton("💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠", callback_data='premium_info'),
             InlineKeyboardButton("📊 𝗦𝗧𝗔𝗧𝗦", callback_data='stats')],
            [InlineKeyboardButton("❓ 𝗛𝗘𝗟𝗣", callback_data='show_help'),
             InlineKeyboardButton("👑 𝗢𝗪𝗡𝗘𝗥", url='https://t.me/trial9pm')],
            [InlineKeyboardButton("👥 𝗚𝗥𝗢𝗨𝗣", url='https://t.me/+otlXZvR0ELRiZDRl'),
             InlineKeyboardButton("🚪 𝗘𝗫𝗜𝗧", callback_data='exit')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        proxies_count = len(self.stripe_processor.proxy_pool)
        
        start_message = (
            "╔═══════════════════════════════════╗\n"
            "║    🔥 <b>TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 𝗣𝗥𝗢</b> 🔥       ║\n"
            "║       <i>𝘗𝘳𝘦𝘮𝘪𝘶𝘮 𝘊𝘊 𝘝𝘢𝘭𝘪??𝘢𝘵𝘪𝘰𝘯</i>        ║\n"
            "╠═══════════════════════════════════╣\n"
            f"║  👤 <b>𝗨𝘀𝗲𝗿:</b> {user.first_name[:15]}\n"
            f"║  🆔 <b>𝗜𝗗:</b> <code>{user.id}</code>\n"
            "╠═══════════════════════════════════╣\n"
            "║         ✨ <b>𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦</b> ✨      ║\n"
            "╠═══════════════════════════════════╣\n"
            "║  ⚡ 5 𝗣𝗼𝘄𝗲𝗿𝗳𝘂𝗹 𝗚𝗮𝘁𝗲𝘀 (𝗔𝘂𝘁𝗵 + 𝗖𝗵𝗮𝗿𝗴𝗲)\n"
            "║  🚀 𝗟𝗶𝗴𝗵𝘁𝗻𝗶𝗻𝗴 𝗙𝗮𝘀𝘁 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴\n"
            "║  📁 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸 𝗦𝘂𝗽𝗽𝗼𝗿𝘁 (𝟭𝟬𝟬𝟬+)\n"
            f"║  🔄 {proxies_count} 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗣𝗿𝗼𝘅𝗶𝗲𝘀\n"
            "║  🧹 𝗔𝗱𝘃𝗮𝗻𝗰𝗲𝗱 𝗖𝗹𝗲𝗮𝗻𝗶𝗻𝗴 𝗧𝗼𝗼𝗹𝘀\n"
            "║  🔍 𝗕𝗜𝗡 𝗟𝗼𝗼𝗸𝘂𝗽 & 𝗜𝗻𝗳𝗼\n"
            "╠═══════════════════════════════════╣\n"
            "║  💳 <b>𝗦𝗨𝗣𝗣𝗢𝗥𝗧𝗘𝗗 𝗚𝗔𝗧𝗘𝗦</b>\n"
            "║  ├─ 🔐 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵\n"
            "║  ├─ 💵 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲 $𝟱\n"
            "║  ├─ 🇮🇳 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 ₹𝟭\n"
            "║  ├─ 🛒 𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗔𝘂𝘁𝗼\n"
            "║  └─ 🧠 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 $𝟭\n"
            "╠═══════════════════════════════════╣\n"
            "║  📋 𝗨𝘀𝗲 /cmds 𝘁𝗼 𝘀𝗲𝗲 𝗮𝗹𝗹 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀\n"
            "╠═══════════════════════════════════╣\n"
            "║     🌟 <i>𝘚𝘦𝘭𝘦𝘤𝘵 𝘢𝘯 𝘰𝘱𝘵𝘪𝘰𝘯 𝘣𝘦𝘭𝘰𝘸</i> 🌟    ║\n"
            "╚═══════════════════════════════════╝"
        )
        await update.message.reply_text(start_message, reply_markup=reply_markup, parse_mode='HTML')

    async def addadmin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a new admin by user ID or by replying to their message"""
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("⛔ This command is restricted to admins only!")
            return
        
        target_user_id = None
        target_name = None
        
        # Check if replying to a message
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            target_user_id = target_user.id
            target_name = target_user.full_name or target_user.username or str(target_user_id)
        # Check if user ID provided as argument
        elif context.args and len(context.args) >= 1:
            try:
                target_user_id = int(context.args[0])
                target_name = str(target_user_id)
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID! Use: /addadmin <user_id> or reply to a message")
                return
        else:
            await update.message.reply_text(
                "❌ <b>Usage:</b>\n"
                "<code>/addadmin user_id</code> - Add by ID\n"
                "<code>/addadmin</code> (reply) - Add by reply",
                parse_mode='HTML'
            )
            return
        
        # Check if already admin
        if target_user_id in self.admin_ids:
            await update.message.reply_text(f"⚠️ User {target_name} is already an admin!")
            return
        
        # Add to admin list
        self.admin_ids.append(target_user_id)
        await update.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ 𝙰𝙳𝙼𝙸𝙽 𝙰𝙳𝙳𝙴𝙳\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"𝗡𝗮𝗺𝗲 ⌁ {target_name}\n"
            f"𝗜𝗗 ⌁ <code>{target_user_id}</code>\n"
            f"𝗧𝗼𝘁𝗮𝗹 ⌁ {len(self.admin_ids)} Admins\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode='HTML'
        )
        
        # Notify the new admin
        try:
            await self.application.bot.send_message(
                chat_id=target_user_id,
                text="🎉 You have been granted admin privileges!\n"
                     "You now have access to all admin commands."
            )
        except Exception as e:
            logger.warning(f"Could not notify new admin: {e}")

    async def removeadmin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove an admin by user ID"""
        user = update.effective_user
        if user.id != self.admin_id:  # Only main admin can remove admins
            await update.message.reply_text("⛔ Only the main admin can remove other admins!")
            return
        
        target_user_id = None
        
        # Check if replying to a message
        if update.message.reply_to_message:
            target_user_id = update.message.reply_to_message.from_user.id
        elif context.args and len(context.args) >= 1:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID!")
                return
        else:
            await update.message.reply_text("❌ Usage: /rmadmin <user_id> or reply to message")
            return
        
        if target_user_id == self.admin_id:
            await update.message.reply_text("⛔ Cannot remove the main admin!")
            return
        
        if target_user_id not in self.admin_ids:
            await update.message.reply_text("⚠️ This user is not an admin!")
            return
        
        self.admin_ids.remove(target_user_id)
        await update.message.reply_text(f"✅ Admin {target_user_id} has been removed!")

    async def listadmins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all current admins"""
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        admin_list = "\n".join([f"⌁ <code>{aid}</code>" + (" (𝙼𝚊𝚒𝚗)" if aid == self.admin_id else "") for aid in self.admin_ids])
        await update.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 𝙰𝙳𝙼𝙸𝙽 𝙻𝙸𝚂𝚃\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{admin_list}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝗧𝗼𝘁𝗮𝗹 ⌁ {len(self.admin_ids)} Admins",
            parse_mode='HTML'
        )

    async def listalloweduser_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all allowed users (with any subscription record)"""
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("⛔ This command is restricted to admins only!")
            return
        
        users = list(self.users_col.find())
        
        if not users:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "👥 𝙰𝙻𝙻𝙾𝚆𝙴𝙳 𝚄𝚂𝙴𝚁𝚂\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "❌ No allowed users found.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode='HTML'
            )
            return
        
        user_list = []
        for u in users:
            user_id = u.get('user_id', 'N/A')
            name = u.get('first_name', '') or u.get('username', '') or 'Unknown'
            username = u.get('username', '')
            profile_link = f"tg://user?id={user_id}"
            expires = u.get('expires_at')
            status = "🟢 Active" if expires and expires > datetime.now() else "🔴 Expired"
            
            user_list.append(
                f"├─ 𝗡𝗮𝗺𝗲: <a href='{profile_link}'>{name}</a>\n"
                f"│  𝗜𝗗: <code>{user_id}</code>\n"
                f"│  𝗦𝘁𝗮𝘁𝘂𝘀: {status}\n"
            )
        
        response = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👥 𝙰𝙻𝙻𝙾𝚆𝙴𝙳 𝚄𝚂𝙴𝚁𝚂\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            + "\n".join(user_list) +
            f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝗧𝗼𝘁𝗮𝗹 ⌁ {len(users)} Users"
        )
        
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000], parse_mode='HTML', disable_web_page_preview=True)
        else:
            await update.message.reply_text(response, parse_mode='HTML', disable_web_page_preview=True)

    async def listsubscription_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List users with active subscriptions"""
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("⛔ This command is restricted to admins only!")
            return
        
        now = datetime.now()
        active_users = list(self.users_col.find({'expires_at': {'$gt': now}}))
        
        if not active_users:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "💎 𝙰𝙲𝚃𝙸𝚅𝙴 𝚂𝚄𝙱𝚂𝙲𝚁𝙸𝙿𝚃𝙸𝙾𝙽𝚂\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "❌ No active subscriptions found.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode='HTML'
            )
            return
        
        user_list = []
        for u in active_users:
            user_id = u.get('user_id', 'N/A')
            name = u.get('first_name', '') or u.get('username', '') or 'Unknown'
            profile_link = f"tg://user?id={user_id}"
            expires = u.get('expires_at')
            days_left = (expires - now).days if expires else 0
            exp_date = expires.strftime('%Y-%m-%d') if expires else 'N/A'
            
            user_list.append(
                f"├─ 𝗡𝗮𝗺𝗲: <a href='{profile_link}'>{name}</a>\n"
                f"│  𝗜𝗗: <code>{user_id}</code>\n"
                f"│  𝗘𝘅𝗽𝗶𝗿𝗲𝘀: {exp_date} ({days_left} days)\n"
            )
        
        response = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💎 𝙰𝙲𝚃𝙸𝚅𝙴 𝚂𝚄𝙱𝚂𝙲𝚁𝙸𝙿𝚃𝙸𝙾𝙽𝚂\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            + "\n".join(user_list) +
            f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝗧𝗼𝘁𝗮𝗹 ⌁ {len(active_users)} Active Subscribers"
        )
        
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000], parse_mode='HTML', disable_web_page_preview=True)
        else:
            await update.message.reply_text(response, parse_mode='HTML', disable_web_page_preview=True)

    async def fproxies_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Format proxies from host:port:user:pass to http://user:pass@host:port"""
        proxies_text = ""
        
        if update.message.reply_to_message:
            if update.message.reply_to_message.document:
                file = await update.message.reply_to_message.document.get_file()
                file_bytes = await file.download_as_bytearray()
                proxies_text = file_bytes.decode('utf-8', errors='ignore')
            elif update.message.reply_to_message.text:
                proxies_text = update.message.reply_to_message.text
        elif context.args:
            proxies_text = " ".join(context.args)
        else:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔄 𝙵𝙾𝚁𝙼𝙰𝚃 𝙿𝚁𝙾𝚇𝙸𝙴𝚂\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📋 <b>Usage:</b>\n"
                "<code>/fproxies host:port:user:pass</code>\n\n"
                "Or reply to a message/file with proxies\n\n"
                "<b>Input format:</b>\n"
                "<code>host:port:username:password</code>\n\n"
                "<b>Output format:</b>\n"
                "<code>http://username:password@host:port</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode='HTML'
            )
            return
        
        lines = proxies_text.strip().split('\n')
        formatted_proxies = []
        failed = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('http://') or line.startswith('https://'):
                formatted_proxies.append(line)
                continue
            
            parts = line.split(':')
            if len(parts) == 4:
                host, port, user, passwd = parts
                formatted_proxies.append(f"http://{user}:{passwd}@{host}:{port}")
            elif len(parts) == 2:
                formatted_proxies.append(f"http://{line}")
            else:
                failed += 1
        
        if not formatted_proxies:
            await update.message.reply_text("❌ No valid proxies found to format!")
            return
        
        result_text = "\n".join(formatted_proxies)
        
        if len(result_text) > 4000:
            from io import BytesIO
            file_buffer = BytesIO(result_text.encode('utf-8'))
            file_buffer.name = "formatted_proxies.txt"
            await update.message.reply_document(
                document=file_buffer,
                caption=(
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ 𝙿𝚁𝙾𝚇𝙸𝙴𝚂 𝙵𝙾𝚁𝙼𝙰𝚃𝚃𝙴𝙳\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"𝗦𝘂𝗰𝗰𝗲𝘀𝘀 ⌁ {len(formatted_proxies)}\n"
                    f"𝗙𝗮𝗶𝗹𝗲𝗱 ⌁ {failed}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                )
            )
        else:
            await update.message.reply_text(
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ 𝙿𝚁𝙾𝚇𝙸𝙴𝚂 𝙵𝙾𝚁𝙼𝙰𝚃𝚃𝙴𝙳\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<code>{result_text}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"𝗦𝘂𝗰𝗰𝗲𝘀𝘀 ⌁ {len(formatted_proxies)}\n"
                f"𝗙𝗮𝗶𝗹𝗲𝗱 ⌁ {failed}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode='HTML'
            )

    def get_gates_message(self):
        total_gates = 5
        gates_on = 5
        gates_off = 0
        maintenance = 0
        
        return (
            "╔══════════════════════════════╗\n"
            "║    ⚔️ <b>𝗚𝗔𝗧𝗘𝗦 𝗦𝗧𝗔𝗧𝗨𝗦</b> ⚔️     ║\n"
            "╠══════════════════════════════╣\n"
            f"║  📊 𝗧𝗼𝘁𝗮𝗹 𝗚𝗮𝘁𝗲𝘀: <b>{total_gates}</b>\n"
            f"║  ✅ 𝗢𝗻𝗹𝗶𝗻𝗲: <b>{gates_on}</b>\n"
            f"║  ❌ 𝗢𝗳𝗳𝗹𝗶𝗻𝗲: <b>{gates_off}</b>\n"
            f"║  ⚠️ 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲: <b>{maintenance}</b>\n"
            "╠══════════════════════════════╣\n"
            "║  🎯 <i>𝘚𝘦𝘭𝘦𝘤𝘵 𝘢 𝘤𝘢𝘵𝘦𝘨𝘰𝘳𝘺 𝘣𝘦𝘭𝘰𝘸</i>  ║\n"
            "╚══════════════════════════════╝"
        )

    def get_gates_keyboard(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔐 𝗔𝗨𝗧𝗛 𝗚𝗔𝗧𝗘𝗦", callback_data='auth_gates'),
             InlineKeyboardButton("💰 𝗖𝗛𝗔𝗥𝗚𝗘 𝗚𝗔𝗧𝗘𝗦", callback_data='charged_gates')],
            [InlineKeyboardButton("📁 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞", callback_data='mass_gates')],
            [InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗠𝗘𝗡𝗨", callback_data='return_main')]
        ])

    def get_auth_gates_message(self):
        return (
            "╔══════════════════════════════╗\n"
            "║    🔐 <b>𝗔𝗨𝗧𝗛 𝗚𝗔𝗧𝗘𝗦</b> 🔐       ║\n"
            "╠══════════════════════════════╣\n"
            "║                              ║\n"
            "║  ⚡ <b>𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵</b> ✅\n"
            "║  ├─ 𝗧𝘆𝗽𝗲: 𝗔𝘂𝘁𝗵𝗲𝗻𝘁𝗶𝗰𝗮𝘁𝗶𝗼𝗻\n"
            "║  ├─ 𝗦𝗽𝗲𝗲𝗱: ⚡ 𝗙𝗮𝘀𝘁\n"
            "║  └─ 𝗖𝗺𝗱: <code>/chk cc|mm|yy|cvv</code>\n"
            "║                              ║\n"
            "╚══════════════════════════════╝"
        )

    def get_charged_gates_message(self):
        return (
            "╔══════════════════════════════╗\n"
            "║   💰 <b>𝗖𝗛𝗔𝗥𝗚𝗘 𝗚𝗔𝗧𝗘𝗦</b> 💰     ║\n"
            "╠══════════════════════════════╣\n"
            "║                              ║\n"
            "║  💵 <b>𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲</b> ✅\n"
            "║  ├─ 𝗔𝗺𝗼𝘂𝗻𝘁: <b>$5 USD</b>\n"
            "║  └─ 𝗖𝗺𝗱: <code>/sc cc|mm|yy|cvv</code>\n"
            "║                              ║\n"
            "║  🇮🇳 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆</b> ✅\n"
            "║  ├─ 𝗔𝗺𝗼𝘂𝗻𝘁: <b>₹1 INR</b>\n"
            "║  └─ 𝗖𝗺𝗱: <code>/rzp cc|mm|yy|cvv</code>\n"
            "║                              ║\n"
            "║  🛒 <b>𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗔𝘂𝘁𝗼</b> ✅\n"
            "║  ├─ 𝗧𝘆𝗽𝗲: 𝗔𝘂𝘁𝗼 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁\n"
            "║  └─ 𝗖𝗺𝗱: <code>/ash cc|mm|yy|cvv</code>\n"
            "║                              ║\n"
            "║  🧠 <b>𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝗕𝟯</b> ✅\n"
            "║  ├─ 𝗔𝗺𝗼𝘂𝗻𝘁: <b>$1 USD</b>\n"
            "║  └─ 𝗖𝗺𝗱: <code>/bc cc|mm|yy|cvv</code>\n"
            "║                              ║\n"
            "╚══════════════════════════════╝"
        )

    def get_mass_gates_message(self):
        return (
            "╔══════════════════════════════╗\n"
            "║   📁 <b>𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞</b> 📁       ║\n"
            "╠══════════════════════════════╣\n"
            "║                              ║\n"
            "║  ⚡ <b>𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵 𝗠𝗮𝘀𝘀</b> ✅\n"
            "║  └─ 𝗖𝗺𝗱: <code>/fchk</code> (𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗳𝗶𝗹𝗲)\n"
            "║                              ║\n"
            "║  💵 <b>𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲 𝗠𝗮𝘀𝘀</b> ✅\n"
            "║  └─ 𝗖𝗺𝗱: <code>/msc</code> (𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗳𝗶𝗹𝗲)\n"
            "║                              ║\n"
            "║  🇮🇳 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗠𝗮𝘀𝘀</b> ✅\n"
            "║  └─ 𝗖𝗺𝗱: <code>/mrzp</code> (𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗳𝗶𝗹𝗲)\n"
            "║                              ║\n"
            "║  🛒 <b>𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗠𝗮𝘀𝘀</b> ✅\n"
            "║  ├─ 𝗖𝗺𝗱: <code>/mash</code> (𝘂𝗽 𝘁𝗼 𝟮𝟬 𝗰𝗮𝗿𝗱𝘀)\n"
            "║  └─ 𝗖𝗺𝗱: <code>/ashtxt</code> (𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗳𝗶𝗹𝗲)\n"
            "║                              ║\n"
            "║  🧠 <b>𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝗠𝗮𝘀𝘀</b> ✅\n"
            "║  └─ 𝗖𝗺𝗱: <code>/mbc</code> (𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗳𝗶𝗹𝗲)\n"
            "║                              ║\n"
            "╚══════════════════════════════╝"
        )

    def get_sub_gates_keyboard(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗚𝗔𝗧𝗘𝗦", callback_data='gates')]
        ])

    async def handle_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Command restricted to admin only!")
            return

        command = update.message.text.split()
        if len(command) < 2:
            await update.message.reply_text("❌ Usage: /allow <user_id> or /deny <user_id>")
            return

        action = command[0][1:]
        target_user = command[1]

        if action == 'allow':
            self.users_col.update_one(
                {'user_id': target_user},
                {'$set': {'expires_at': datetime.now() + relativedelta(days=30)}},
                upsert=True
            )
            await update.message.reply_text(f"✅ User {target_user} approved!")
        elif action == 'deny':
            self.users_col.delete_one({'user_id': target_user})
            await update.message.reply_text(f"❌ User {target_user} removed!")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('allow_'):
            user_id = query.data.split('_')[1]
            self.users_col.update_one(
                {'user_id': user_id},
                {'$set': {'expires_at': datetime.now() + relativedelta(days=30)}},
                upsert=True
            )
            await query.edit_message_text(f"✅ User {user_id} approved!")
            await self.application.bot.send_message(
                chat_id=int(user_id),
                text="🎉 Your access has been approved!\n"
                     "Use /start to begin checking cards."
            )
            
        elif query.data.startswith('deny_'):
            user_id = query.data.split('_')[1]
            self.users_col.delete_one({'user_id': user_id})
            await query.edit_message_text(f"❌ User {user_id} denied!")
            
        elif query.data == 'upload':
            if await self.is_user_allowed(query.from_user.id):
                await query.message.reply_text("📤 Please upload your combo file (.txt)")
            else:
                await query.message.reply_text("⛔ You are not authorized!")
                
        elif query.data == 'stats':
            await self.show_stats(update, context)
        elif query.data == 'help' or query.data == 'show_help':
            await self.show_help_callback(query)
        elif query.data == 'cancel':
            await self.stop_command(update, context)
        elif query.data.startswith('g2stop_'):
            target_user_id = int(query.data.split('_')[1])
            if query.from_user.id == target_user_id or query.from_user.id == self.admin_id:
                if target_user_id in self.gate2_active_tasks:
                    self.gate2_stop_flags[target_user_id] = True
                    task = self.gate2_active_tasks[target_user_id]
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    await query.edit_message_text("⏹️ 𝗠𝗮𝘀𝘀 𝗰𝗵𝗲𝗰𝗸 𝘀𝘁𝗼𝗽𝗽𝗲𝗱!")
                else:
                    await query.answer("No active process to stop!")
            else:
                await query.answer("You can only stop your own process!")
        elif query.data.startswith('g2stat_'):
            await query.answer("Stats are updated in real-time!")
        elif query.data.startswith('g1stop_'):
            target_user_id = int(query.data.split('_')[1])
            if query.from_user.id == target_user_id or query.from_user.id == self.admin_id:
                if target_user_id in self.active_tasks:
                    self.stop_flags[target_user_id] = True
                    task = self.active_tasks[target_user_id]
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    await query.edit_message_text("⏹️ 𝗠𝗮𝘀𝘀 𝗰𝗵𝗲𝗰𝗸 𝘀𝘁𝗼𝗽𝗽𝗲𝗱!")
                else:
                    await query.answer("No active process to stop!")
            else:
                await query.answer("You can only stop your own process!")
        elif query.data.startswith('g1stat_'):
            await query.answer("Stats are updated in real-time!")
        elif query.data.startswith('g3stop_'):
            target_user_id = int(query.data.split('_')[1])
            if query.from_user.id == target_user_id or query.from_user.id == self.admin_id:
                if target_user_id in self.gate3_active_tasks:
                    self.gate3_stop_flags[target_user_id] = True
                    task = self.gate3_active_tasks[target_user_id]
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    await query.edit_message_text("⏹️ 𝗠𝗮𝘀𝘀 𝗰𝗵𝗲𝗰𝗸 𝘀𝘁𝗼𝗽𝗽𝗲𝗱!")
                else:
                    await query.answer("No active process to stop!")
            else:
                await query.answer("You can only stop your own process!")
        elif query.data.startswith('g3stat_'):
            await query.answer("Stats are updated in real-time!")
        elif query.data.startswith('g4stop_'):
            target_user_id = int(query.data.split('_')[1])
            if query.from_user.id == target_user_id or query.from_user.id == self.admin_id:
                if target_user_id in self.gate4_active_tasks:
                    self.gate4_stop_flags[target_user_id] = True
                    task = self.gate4_active_tasks[target_user_id]
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    await query.edit_message_text("⏹️ 𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗰𝗵𝗲𝗰𝗸 𝘀𝘁𝗼𝗽𝗽𝗲𝗱!")
                else:
                    await query.answer("No active process to stop!")
            else:
                await query.answer("You can only stop your own process!")
        elif query.data.startswith('g4stat_'):
            await query.answer("Stats are updated in real-time!")
        elif query.data.startswith('g4_use_own_'):
            target_user_id = int(query.data.split('_')[-1])
            if query.from_user.id == target_user_id:
                self.gate4_user_site_choice[target_user_id] = True
                await query.edit_message_text("✅ Using your own sites for checking!")
            else:
                await query.answer("This is not your choice!")
        elif query.data.startswith('g4_use_bot_'):
            target_user_id = int(query.data.split('_')[-1])
            if query.from_user.id == target_user_id:
                self.gate4_user_site_choice[target_user_id] = False
                await query.edit_message_text("✅ Using bot's site list for checking!")
            else:
                await query.answer("This is not your choice!")
        
        elif query.data == 'gates':
            await query.edit_message_text(
                self.get_gates_message(),
                reply_markup=self.get_gates_keyboard(),
                parse_mode='HTML'
            )
        
        elif query.data == 'tools':
            tools_message = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🛠️ 𝚃𝙾𝙾𝙻𝚂 𝙼𝙴𝙽𝚄\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🎰 𝙶𝙴𝙽𝙴𝚁𝙰𝚃𝙾𝚁:\n"
                "🎲 𝗴𝗲𝗻 ⌁ 𝙶𝚎𝚗𝚎𝚛𝚊𝚝𝚎 𝙲𝙲 𝚏𝚛𝚘𝚖 𝙱𝙸𝙽\n"
                "   ╰➤ /gen <bin> [qty]\n\n"
                "📁 𝙵𝙸𝙻𝙴 𝚃𝙾𝙾𝙻𝚂:\n"
                "🗂️ 𝗰𝗹𝗲𝗮𝗻 ⌁ 𝙲𝚕𝚎𝚊𝚗 𝚎𝚖𝚊𝚒𝚕:𝚙𝚊𝚜𝚜 𝚌𝚘𝚖𝚋𝚘𝚜\n"
                "💳 𝗰𝗰𝗻 ⌁ 𝙴𝚡𝚝𝚛𝚊𝚌𝚝 𝚌𝚊𝚛𝚍𝚜 𝚏𝚛𝚘𝚖 𝚏𝚒𝚕𝚎\n"
                "📧 𝘂𝗹𝗽 ⌁ 𝙴𝚡𝚝𝚛𝚊𝚌𝚝 𝚎𝚖𝚊𝚒𝚕:𝚙𝚊𝚜𝚜𝚠𝚘𝚛𝚍\n"
                "🧾 𝘁𝘅𝘁 ⌁ 𝙲𝚘𝚗𝚟𝚎𝚛𝚝 𝚝𝚘 .𝚝𝚡𝚝 𝚏𝚒𝚕𝚎\n"
                "🪚 𝘀𝗽𝗹𝗶𝘁 ⌁ 𝚂𝚙𝚕𝚒𝚝 𝚏𝚒𝚕𝚎 𝚋𝚢 𝚕𝚒𝚗𝚎𝚜\n"
                "🔍 𝗯𝗶𝗻 ⌁ 𝙵𝚒𝚕𝚝𝚎𝚛 𝚌𝚊𝚛𝚍𝚜 𝚋𝚢 𝙱𝙸𝙽\n"
                "🗃️ 𝘀𝗼𝗿𝘁 ⌁ 𝚂𝚘𝚛𝚝 𝚌𝚊𝚛𝚍𝚜 𝚋𝚢 𝚋𝚛𝚊𝚗𝚍\n\n"
                "🌐 𝙿𝚁𝙾𝚇𝚈 𝚃𝙾𝙾𝙻𝚂:\n"
                "🔍 𝗰𝗵𝗸𝗽𝗿𝗼𝘅𝘆 ⌁ 𝙲𝚑𝚎𝚌𝚔 𝚜𝚒𝚗𝚐𝚕𝚎/𝚖𝚞𝚕𝚝𝚒 𝚙𝚛𝚘𝚡𝚒𝚎𝚜\n"
                "🔄 𝗰𝗹𝗽 ⌁ 𝙲𝚑𝚎𝚌𝚔 & 𝚌𝚕𝚎𝚊𝚗 𝚕𝚘𝚊𝚍𝚎𝚍 𝚙𝚛𝚘𝚡𝚒𝚎𝚜\n"
                "📄 𝗽𝘁𝘅𝘁 ⌁ 𝙲𝚑𝚎𝚌𝚔 𝚙𝚛𝚘𝚡𝚒𝚎𝚜 𝚏𝚛𝚘𝚖 𝚏𝚒𝚕𝚎\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📌 𝗨𝘀𝗮𝗴𝗲 ⌁ 𝚁𝚎𝚙𝚕𝚢 𝚝𝚘 𝚏𝚒𝚕𝚎 𝚠𝚒𝚝𝚑 𝚌𝚘𝚖𝚖𝚊𝚗𝚍\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            keyboard = [[InlineKeyboardButton("🔙 𝔅𝔞𝔠𝔨", callback_data='back_to_start')]]
            await query.edit_message_text(tools_message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif query.data == 'back_to_start':
            user = query.from_user
            proxies_count = len(self.stripe_processor.proxy_pool)
            keyboard = [
                [InlineKeyboardButton("⚔️ 𝗚𝗔𝗧𝗘𝗦", callback_data='gates'),
                 InlineKeyboardButton("🛠️ 𝗧𝗢𝗢𝗟𝗦", callback_data='tools')],
                [InlineKeyboardButton("💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠", callback_data='premium_info'),
                 InlineKeyboardButton("📊 𝗦𝗧𝗔𝗧𝗦", callback_data='stats')],
                [InlineKeyboardButton("❓ 𝗛𝗘𝗟𝗣", callback_data='show_help'),
                 InlineKeyboardButton("👑 𝗢𝗪𝗡𝗘𝗥", url='https://t.me/trial9pm')],
                [InlineKeyboardButton("👥 𝗚𝗥𝗢𝗨𝗣", url='https://t.me/+otlXZvR0ELRiZDRl'),
                 InlineKeyboardButton("🚪 𝗘𝗫𝗜𝗧", callback_data='exit')]
            ]
            start_message = (
                "╔═══════════════════════════════════╗\n"
                "║    🔥 <b>TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 𝗣𝗥𝗢</b> 🔥       ║\n"
                "║       <i>𝘗𝘳𝘦𝘮𝘪𝘶𝘮 𝘊𝘊 𝘝𝘢𝘭𝘪𝘥𝘢𝘵𝘪𝘰𝘯</i>        ║\n"
                "╠═══════════════════════════════════╣\n"
                f"║  👤 <b>𝗨𝘀𝗲𝗿:</b> {user.first_name[:15]}\n"
                f"║  🆔 <b>𝗜𝗗:</b> <code>{user.id}</code>\n"
                "╠═══════════════════════════════════╣\n"
                "║         ✨ <b>𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦</b> ✨      ║\n"
                "╠═══════════════════════════════════╣\n"
                "║  ⚡ 5 𝗣𝗼𝘄𝗲𝗿𝗳𝘂𝗹 𝗚𝗮𝘁𝗲𝘀 (𝗔𝘂𝘁𝗵 + 𝗖𝗵𝗮𝗿𝗴𝗲)\n"
                "║  🚀 𝗟𝗶𝗴𝗵𝘁𝗻𝗶𝗻𝗴 𝗙𝗮𝘀𝘁 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴\n"
                "║  📁 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸 𝗦𝘂𝗽𝗽𝗼𝗿𝘁 (𝟭𝟬𝟬𝟬+)\n"
                f"║  🔄 {proxies_count} 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗣𝗿𝗼𝘅𝗶𝗲𝘀\n"
                "╠═══════════════════════════════════╣\n"
                "║  📋 𝗨𝘀𝗲 /cmds 𝘁𝗼 𝘀𝗲𝗲 𝗮𝗹𝗹 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀\n"
                "╠═══════════════════════════════════╣\n"
                "║     🌟 <i>𝘚𝘦𝘭𝘦𝘤𝘵 𝘢𝘯 𝘰𝘱𝘵𝘪𝘰𝘯 𝘣𝘦𝘭𝘰𝘸</i> 🌟    ║\n"
                "╚═══════════════════════════════════╝"
            )
            await query.edit_message_text(start_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
        elif query.data == 'group':
            await query.answer("Join our group for updates!")
            await query.message.reply_text(
                "👥 𝗝𝗼𝗶𝗻 𝗢𝘂𝗿 𝗚𝗿𝗼𝘂𝗽\n"
                "- - - - - - - - - - - - - - - -\n"
                "╰➤ https://t.me/trial9pm"
            )
        
        elif query.data == 'exit':
            await query.message.delete()
        
        elif query.data == 'premium_info':
            premium_text = (
                "╔══════════════════════════════════╗\n"
                "║    💎 <b>𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗣𝗟𝗔𝗡𝗦</b> 💎       ║\n"
                "╠══════════════════════════════════╣\n"
                "║                                  ║\n"
                "║  🥉 <b>𝗕𝗥𝗢𝗡𝗭𝗘</b> - 7 𝗗𝗮𝘆𝘀\n"
                "║  └─ 𝗣𝗿𝗶𝗰𝗲: <b>$5 USD</b>\n"
                "║                                  ║\n"
                "║  🥈 <b>𝗦𝗜𝗟𝗩𝗘𝗥</b> - 30 𝗗𝗮𝘆𝘀\n"
                "║  └─ 𝗣𝗿𝗶𝗰𝗲: <b>$15 USD</b>\n"
                "║                                  ║\n"
                "║  🥇 <b>𝗚𝗢𝗟𝗗</b> - 90 𝗗𝗮𝘆𝘀\n"
                "║  └─ 𝗣𝗿𝗶𝗰𝗲: <b>$35 USD</b>\n"
                "║                                  ║\n"
                "║  💠 <b>𝗗𝗜𝗔𝗠𝗢𝗡𝗗</b> - 𝗟𝗶𝗳𝗲𝘁𝗶𝗺𝗲\n"
                "║  └─ 𝗣𝗿𝗶𝗰𝗲: <b>$100 USD</b>\n"
                "╠══════════════════════════════════╣\n"
                "║       ✨ <b>𝗔𝗟𝗟 𝗣𝗟𝗔𝗡𝗦 𝗜𝗡𝗖𝗟𝗨𝗗𝗘</b> ✨     ║\n"
                "╠══════════════════════════════════╣\n"
                "║  ✅ 𝗔𝗹𝗹 5 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗚𝗮𝘁𝗲𝘀\n"
                "║  ✅ 𝗨𝗻𝗹𝗶𝗺𝗶𝘁𝗲𝗱 𝗖𝗵𝗲𝗰𝗸𝘀\n"
                "║  ✅ 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸 𝗦𝘂𝗽𝗽𝗼𝗿𝘁\n"
                "║  ✅ 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗣𝗿𝗼𝘅𝗶𝗲𝘀\n"
                "║  ✅ 𝗣𝗿𝗶𝗼𝗿𝗶𝘁𝘆 𝗦𝘂𝗽𝗽𝗼𝗿𝘁\n"
                "╠══════════════════════════════════╣\n"
                "║  📩 𝗖𝗼𝗻𝘁𝗮𝗰𝘁: @trial9pm\n"
                "╚══════════════════════════════════╝"
            )
            keyboard = [
                [InlineKeyboardButton("💳 𝗕𝗨𝗬 𝗡𝗢𝗪", url='https://t.me/trial9pm')],
                [InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞", callback_data='return_main')]
            ]
            await query.edit_message_text(premium_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
        elif query.data == 'auth_gates':
            await query.edit_message_text(
                self.get_auth_gates_message(),
                reply_markup=self.get_sub_gates_keyboard(),
                parse_mode='HTML'
            )
        
        elif query.data == 'charged_gates':
            await query.edit_message_text(
                self.get_charged_gates_message(),
                reply_markup=self.get_sub_gates_keyboard(),
                parse_mode='HTML'
            )
        
        elif query.data == 'mass_gates':
            await query.edit_message_text(
                self.get_mass_gates_message(),
                reply_markup=self.get_sub_gates_keyboard(),
                parse_mode='HTML'
            )
        
        elif query.data == 'return_main':
            user = query.from_user
            proxies_count = len(self.stripe_processor.proxy_pool)
            keyboard = [
                [InlineKeyboardButton("⚔️ 𝗚𝗔𝗧𝗘𝗦", callback_data='gates'),
                 InlineKeyboardButton("🛠️ 𝗧𝗢𝗢𝗟𝗦", callback_data='tools')],
                [InlineKeyboardButton("💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠", callback_data='premium_info'),
                 InlineKeyboardButton("📊 𝗦𝗧𝗔𝗧𝗦", callback_data='stats')],
                [InlineKeyboardButton("❓ 𝗛𝗘𝗟𝗣", callback_data='show_help'),
                 InlineKeyboardButton("👑 𝗢𝗪𝗡𝗘𝗥", url='https://t.me/trial9pm')],
                [InlineKeyboardButton("👥 𝗚𝗥𝗢𝗨𝗣", url='https://t.me/+otlXZvR0ELRiZDRl'),
                 InlineKeyboardButton("🚪 𝗘𝗫𝗜𝗧", callback_data='exit')]
            ]
            start_message = (
                "╔═══════════════════════════════════╗\n"
                "║    🔥 <b>TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 𝗣𝗥𝗢</b> 🔥       ║\n"
                "║       <i>𝘗𝘳𝘦𝘮𝘪𝘶𝘮 𝘊𝘊 𝘝𝘢𝘭𝘪𝘥𝘢𝘵𝘪𝘰𝘯</i>        ║\n"
                "╠═══════════════════════════════════╣\n"
                f"║  👤 <b>𝗨𝘀𝗲𝗿:</b> {user.first_name[:15]}\n"
                f"║  🆔 <b>𝗜𝗗:</b> <code>{user.id}</code>\n"
                "╠═══════════════════════════════════╣\n"
                "║         ✨ <b>𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦</b> ✨      ║\n"
                "╠═══════════════════════════════════╣\n"
                "║  ⚡ 5 𝗣𝗼𝘄𝗲𝗿𝗳𝘂𝗹 𝗚𝗮𝘁𝗲𝘀 (𝗔𝘂𝘁𝗵 + 𝗖𝗵𝗮𝗿𝗴𝗲)\n"
                "║  🚀 𝗟𝗶𝗴𝗵𝘁𝗻𝗶𝗻𝗴 𝗙𝗮𝘀𝘁 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴\n"
                "║  📁 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸 𝗦𝘂𝗽𝗽𝗼𝗿𝘁 (𝟭𝟬𝟬𝟬+)\n"
                f"║  🔄 {proxies_count} 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗣𝗿𝗼𝘅𝗶𝗲𝘀\n"
                "╠═══════════════════════════════════╣\n"
                "║  📋 𝗨𝘀𝗲 /cmds 𝘁𝗼 𝘀𝗲𝗲 𝗮𝗹𝗹 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀\n"
                "╠═══════════════════════════════════╣\n"
                "║     🌟 <i>𝘚𝘦𝘭𝘦𝘤𝘵 𝘢𝘯 𝘰𝘱𝘵𝘪𝘰𝘯 𝘣𝘦𝘭𝘰𝘸</i> 🌟    ║\n"
                "╚═══════════════════════════════════╝"
            )
            await query.edit_message_text(
                start_message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        message = ' '.join(context.args)
        if not message:
            await update.message.reply_text("Usage: /broadcast Your message here")
            return
        
        users = self.users_col.find()
        success = 0
        failed = 0
        for user in users:
            try:
                await self.application.bot.send_message(
                    chat_id=int(user['user_id']),
                    text=f"📢 Admin Broadcast:\n\n{message}"
                )
                success += 1
            except:
                failed += 1
        await update.message.reply_text(f"Broadcast complete:\n✅ Success: {success}\n❌ Failed: {failed}")

    async def genkey_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /genkey <duration>\nDurations: 1d, 7d, 1m")
            return
        
        duration = context.args[0].lower()
        key_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
        key_code = ''.join(random.choices(string.digits, k=2))
        key = f"OG-CHECKER-{key_id}-{key_code}"
        
        delta = self.parse_duration(duration)
        if not delta:
            await update.message.reply_text("Invalid duration! Use 1d, 7d, or 1m")
            return
        
        self.keys_col.insert_one({
            'key': key,
            'duration_days': delta.days,
            'used': False,
            'created_at': datetime.now()
        })
        
        duration_text = f"{delta.days} Day{'s' if delta.days > 1 else ''}"
        await update.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 𝙺𝙴𝚈 𝙶𝙴𝙽𝙴𝚁𝙰𝚃𝙴𝙳\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"𝗞𝗲𝘆 ⌁ <code>{key}</code>\n"
            f"𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 ⌁ {duration_text}\n"
            f"𝗖𝗿𝗲𝗮𝘁𝗲𝗱 ⌁ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ Unused\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝚄𝚜𝚎 /redeem {key} 𝚝𝚘 𝚊𝚌𝚝𝚒𝚟𝚊𝚝𝚎",
            parse_mode='HTML'
        )

    def parse_duration(self, duration):
        if duration.endswith('d'):
            days = int(duration[:-1])
            return relativedelta(days=days)
        if duration.endswith('m'):
            months = int(duration[:-1])
            return relativedelta(months=months)
        return None

    async def redeem_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not context.args:
            await update.message.reply_text("Usage: /redeem <key>")
            return
        
        key = context.args[0].upper()
        key_data = self.keys_col.find_one({'key': key, 'used': False})
        
        if not key_data:
            await update.message.reply_text("❌ Invalid or expired key!")
            return
        
        expires_at = datetime.now() + relativedelta(days=key_data['duration_days'])
        self.users_col.update_one(
            {'user_id': str(user.id)},
            {'$set': {
                'user_id': str(user.id),
                'username': user.username,
                'full_name': user.full_name,
                'expires_at': expires_at
            }},
            upsert=True
        )
        
        self.keys_col.update_one({'key': key}, {'$set': {'used': True}})
        
        days_left = (expires_at - datetime.now()).days
        await update.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎉 𝙺𝙴𝚈 𝚁𝙴𝙳𝙴𝙴𝙼𝙴𝙳\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"𝗨𝘀𝗲𝗿 ⌁ {user.first_name}\n"
            f"𝗜𝗗 ⌁ <code>{user.id}</code>\n"
            f"𝗞𝗲𝘆 ⌁ <code>{key}</code>\n\n"
            f"𝗘𝘅𝗽𝗶𝗿𝗲𝘀 ⌁ {expires_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"𝗗𝗮𝘆𝘀 𝗟𝗲𝗳𝘁 ⌁ {days_left} Day{'s' if days_left > 1 else ''}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝙴𝚗𝚓𝚘𝚢 𝚢𝚘𝚞𝚛 𝚙𝚛𝚎𝚖𝚒𝚞𝚖 𝚊𝚌𝚌𝚎𝚜𝚜! ⚔️",
            parse_mode='HTML'
        )

    async def delkey_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete a key or revoke user subscription"""
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        if not context.args:
            await update.message.reply_text(
                "<b>❌ Usage:</b>\n"
                "<code>/delkey KEY</code> - Delete unused key\n"
                "<code>/delkey user ID</code> - Revoke user subscription\n\n"
                "<b>Examples:</b>\n"
                "<code>/delkey OG-CHECKER-ABC-12</code>\n"
                "<code>/delkey user 123456789</code>",
                parse_mode='HTML'
            )
            return
        
        # Check if revoking user subscription
        if context.args[0].lower() == 'user' and len(context.args) >= 2:
            try:
                target_user_id = context.args[1]
                result = self.users_col.delete_one({'user_id': target_user_id})
                if result.deleted_count > 0:
                    await update.message.reply_text(
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🗑️ 𝚂𝚄𝙱𝚂𝙲𝚁𝙸𝙿𝚃𝙸𝙾𝙽 𝚁𝙴𝚅𝙾𝙺𝙴𝙳\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"𝗨𝘀𝗲𝗿 𝗜𝗗 ⌁ <code>{target_user_id}</code>\n"
                        f"𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ Subscription removed\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━",
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(f"⚠️ User {target_user_id} not found in database!")
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {str(e)}")
            return
        
        # Delete key
        key = context.args[0].upper()
        key_data = self.keys_col.find_one({'key': key})
        
        if not key_data:
            await update.message.reply_text(f"⚠️ Key <code>{key}</code> not found!", parse_mode='HTML')
            return
        
        status = "Used" if key_data.get('used', False) else "Unused"
        self.keys_col.delete_one({'key': key})
        
        await update.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🗑️ 𝙺𝙴𝚈 𝙳𝙴𝙻𝙴𝚃𝙴𝙳\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"𝗞𝗲𝘆 ⌁ <code>{key}</code>\n"
            f"𝗪𝗮𝘀 ⌁ {status}\n"
            f"𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ Deleted\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode='HTML'
        )

    async def addproxy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add proxies to the proxy list"""
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        if not context.args:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🌐 𝙰𝙳𝙳 𝙿𝚁𝙾𝚇𝚈\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "𝗨𝘀𝗮𝗴𝗲 ⌁ /addproxy proxy1 proxy2 ...\n\n"
                "𝗙𝗼𝗿𝗺𝗮𝘁 ⌁ ip:port:user:pass\n"
                "𝗢𝗿 ⌁ http://user:pass@ip:port\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "𝙽𝚘 𝚕𝚒𝚖𝚒𝚝 - 𝚊𝚍𝚍 𝚊𝚜 𝚖𝚊𝚗𝚢 𝚊𝚜 𝚢𝚘𝚞 𝚠𝚊𝚗𝚝",
                parse_mode='HTML'
            )
            return
        
        proxies_to_add = context.args
        added_count = 0
        
        try:
            with open('proxies.txt', 'a') as f:
                for proxy in proxies_to_add:
                    proxy = proxy.strip()
                    if proxy:
                        f.write(f"{proxy}\n")
                        added_count += 1
            
            # Reload proxies for all gates
            self.stripe_processor.load_proxies()
            self.gate2_processor.load_proxies()
            self.gate3_processor.load_proxies()
            
            # Count total proxies
            with open('proxies.txt', 'r') as f:
                total_proxies = len([line for line in f.readlines() if line.strip()])
            
            await update.message.reply_text(
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ 𝙿𝚁𝙾𝚇𝙸𝙴𝚂 𝙰𝙳𝙳𝙴𝙳\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"𝗔𝗱𝗱𝗲𝗱 ⌁ {added_count} proxies\n"
                f"𝗧𝗼𝘁𝗮𝗹 ⌁ {total_proxies} proxies\n"
                f"𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ Reloaded all gates\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode='HTML'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def reloadproxies_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reload proxies from file for all gates"""
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        try:
            # Reload for all gates
            self.stripe_processor.load_proxies()
            self.gate2_processor.load_proxies()
            self.gate3_processor.load_proxies()
            
            # Reload Gate 4 (Shopify)
            from gate4 import load_proxies as g4_load_proxies, shopify_processor as g4_processor
            new_proxies = g4_load_proxies()
            g4_processor.proxies = new_proxies
            
            # Reload Gate 5 (Braintree/B3)
            from gate5 import processor as g5_processor
            g5_processor.load_proxies()
            
            # Get proxy counts (each gate uses different attribute names)
            g1_count = len(self.stripe_processor.proxy_pool) if hasattr(self.stripe_processor, 'proxy_pool') else 0
            g2_count = len(self.gate2_processor.proxy_list) if hasattr(self.gate2_processor, 'proxy_list') else 0
            g3_count = len(self.gate3_processor.proxy_pool) if hasattr(self.gate3_processor, 'proxy_pool') else 0
            g4_count = len(g4_processor.proxies) if hasattr(g4_processor, 'proxies') else 0
            g5_count = len(g5_processor.proxy_pool) if hasattr(g5_processor, 'proxy_pool') else 0
            
            # Count from file
            with open('proxies.txt', 'r') as f:
                file_count = len([line for line in f.readlines() if line.strip()])
            
            await update.message.reply_text(
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 𝙿𝚁𝙾𝚇𝙸𝙴𝚂 𝚁𝙴𝙻𝙾𝙰𝙳𝙴𝙳\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"𝗙𝗶𝗹𝗲 ⌁ {file_count} proxies\n"
                f"𝗚𝗮𝘁𝗲 𝟭 ⌁ {g1_count} loaded\n"
                f"𝗚𝗮𝘁𝗲 𝟮 ⌁ {g2_count} loaded\n"
                f"𝗚𝗮𝘁𝗲 𝟯 ⌁ {g3_count} loaded\n"
                f"𝗚𝗮𝘁𝗲 𝟰 ⌁ {g4_count} loaded\n"
                f"𝗚𝗮𝘁𝗲 𝟱 ⌁ {g5_count} loaded\n"
                f"𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ All gates reloaded\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        is_admin = user.id == self.admin_id
        
        help_text = """╔═══════════════════════════════╗
       TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 📜 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
╚═══════════════════════════════╝

┌─────────「 🔐 𝗔𝗨𝗧𝗛 𝗚𝗔𝗧𝗘𝗦 」─────────┐
│ <code>/chk</code> ⌁ Stripe Auth (single)
│ <code>/fchk</code> ⌁ Stripe Auth Mass
└────────────────────────────────────┘

┌────────「 💰 𝗖𝗛𝗔𝗥𝗚𝗘 𝗚𝗔𝗧𝗘𝗦 」────────┐
│ <code>/sc</code> ⌁ Stripe Charge $5
│ <code>/msc</code> ⌁ Stripe Mass
│ <code>/rzp</code> ⌁ Razorpay ₹1
│ <code>/mrzp</code> ⌁ Razorpay Mass
│ <code>/bc</code> ⌁ Braintree Charge $1
│ <code>/mbc</code> ⌁ Braintree Charge Mass
└────────────────────────────────────┘

┌────────「 🛒 𝗦𝗛𝗢𝗣𝗜𝗙𝗬 𝗚𝗔𝗧𝗘 」────────┐
│ <code>/ash</code> ⌁ Shopify Auto (single)
│ <code>/mash</code> ⌁ Shopify Mass (20 max)
│ <code>/ashtxt</code> ⌁ Shopify from file
│ <code>/asm</code> ⌁ Shopify Mass Alt
└────────────────────────────────────┘

┌────────「 🌐 𝗦𝗜𝗧𝗘 𝗠𝗚𝗠𝗧 」────────┐
│ <code>/addsite</code> ⌁ Add Shopify site
│ <code>/rmsite</code> ⌁ Remove site
│ <code>/listsite</code> ⌁ List your sites
│ <code>/chksite</code> ⌁ Check if site works
│ <code>/chkaddedsite</code> ⌁ Check added sites
└────────────────────────────────────┘

┌────────「 🧹 𝗧𝗢𝗢𝗟𝗦 」────────┐
│ <code>/clean</code> ⌁ Clean combos
│ <code>/ccn</code> ⌁ Extract valid cards
│ <code>/ulp</code> ⌁ Extract email:pass
│ <code>/txt</code> ⌁ Convert to txt file
│ <code>/split</code> ⌁ Split file into parts
│ <code>/bin</code> ⌁ Filter by BIN prefix
│ <code>/sort</code> ⌁ Sort cards by type
│ <code>/gen</code> ⌁ Generate cards
└────────────────────────────────────┘

┌────────「 🔌 𝗣𝗥𝗢𝗫𝗬 」────────┐
│ <code>/chkproxy</code> ⌁ Check proxy health
│ <code>/clp</code> ⌁ Check live proxies
│ <code>/ptxt</code> ⌁ Proxies to txt
└────────────────────────────────────┘

┌──────────「 ⚙️ 𝗚𝗘𝗡𝗘𝗥𝗔𝗟 」──────────┐
│ <code>/start</code> ⌁ Main menu
│ <code>/help</code> ⌁ This message
│ <code>/info</code> ⌁ Bot statistics
│ <code>/stats</code> ⌁ Your statistics
│ <code>/stop</code> ⌁ Stop current check
│ <code>/redeem</code> ⌁ Redeem access key
└────────────────────────────────────┘"""

        if is_admin:
            help_text += """

┌─────────「 👑 𝗔𝗗𝗠𝗜𝗡 」─────────┐
│ <code>/allow</code> ⌁ Approve user
│ <code>/deny</code> ⌁ Remove user
│ <code>/genkey</code> ⌁ Generate key
│ <code>/broadcast</code> ⌁ Send to all
│ <code>/addadmin</code> ⌁ Add admin
│ <code>/rmadmin</code> ⌁ Remove admin
│ <code>/listadmins</code> ⌁ Show admins
│ <code>/delkey</code> ⌁ Delete key
│ <code>/addproxy</code> ⌁ Add proxies
│ <code>/reloadproxies</code> ⌁ Reload proxies
└────────────────────────────────────┘"""

        help_text += """

┌──────────「 🎯 𝗙𝗢𝗥𝗠𝗔𝗧 」──────────┐
│ <code>4111111111111111|12|25|123</code>
│ <code>4111111111111111|12|2025|123</code>
└────────────────────────────────────┘

💡 <b>𝗧𝗜𝗣:</b> 𝗨𝘀𝗲 <code>.</code> 𝗼𝗿 <code>/</code> 𝗳𝗼𝗿 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀
    ╰─➤ <a href="https://t.me/+otlXZvR0ELRiZDRl">TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥</a> ✿"""

        await self.send_message(update, help_text)

    async def show_help_callback(self, query):
        """Handle help button callback"""
        user = query.from_user
        is_admin = self.is_admin(user.id)
        
        help_text = """╔═══════════════════════════════╗
       TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 🔥 𝗜𝗡𝗙𝗢
╚═══════════════════════════════╝

┌─────────「 ⚡ 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦 」─────────┐
│ ✦ Stripe Auth & Charge Gates
│ ✦ Razorpay Payment Gateway
│ ✦ Braintree Gateway
│ ✦ Shopify Auto Checkout
│ ✦ Mass Check Support
│ ✦ Proxy Rotation
│ ✦ BIN Lookup
└────────────────────────────────────┘

┌─────────「 🔐 𝗔𝗨𝗧𝗛 」─────────┐
│ <code>/chk</code> ⌁ Stripe Auth
│ <code>/fchk</code> ⌁ Stripe Mass
└────────────────────────────────────┘

┌────────「 💰 𝗖𝗛𝗔𝗥𝗚𝗘 」────────┐
│ <code>/sc</code> ⌁ Stripe $5
│ <code>/rzp</code> ⌁ Razorpay ₹1
│ <code>/bc</code> ⌁ Braintree $1
│ <code>/ash</code> ⌁ Shopify Auto
└────────────────────────────────────┘

┌────────「 📁 𝗠𝗔𝗦𝗦 」────────┐
│ <code>/msc</code> <code>/mrzp</code> <code>/mash</code> <code>/ashtxt</code>
└────────────────────────────────────┘

┌────────「 ⚙️ 𝗢𝗧𝗛𝗘𝗥 」────────┐
│ <code>/cmds</code> ⌁ All commands
│ <code>/stats</code> ⌁ Your stats
│ <code>/stop</code> ⌁ Stop check
└────────────────────────────────────┘

💡 <b>𝗧𝗜𝗣:</b> 𝗨𝘀𝗲 <code>.</code> 𝗼𝗿 <code>/</code> 𝗳𝗼𝗿 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀
    ╰─➤ 👑 𝗢𝘄𝗻𝗲𝗿: @trial9pm ✿"""

        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='return_main')]]
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    async def cmds_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.show_help(update, context)

    async def initialize_user_stats(self, user_id):
        if user_id not in self.user_stats:
            self.user_stats[user_id] = {
                'total': 0,
                'approved': 0,
                'declined': 0,
                '3ds': 0,
                'checked': 0,
                'approved_ccs': [],
                'last_response': 'Starting...',
                'start_time': datetime.now()
            }

    def extract_card_from_text(self, text):
        """Extract card details from any text message"""
        patterns = [
            # Standard format: 4111111111111111|12|2025|123
            r'(\d{13,19})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})',
            # Format with name: 4111111111111111|12|2025|123|John Doe
            r'(\d{13,19})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})[|\s/-]+(.+)',
            # Format with spaces: 4111 1111 1111 1111|12|2025|123
            r'(\d{4}\s?\d{4}\s?\d{4}\s?\d{3,4})[|\s/-]+(\d{1,2})[|\s/-]+(\d{2,4})[|\s/-]+(\d{3,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 4:
                    card = groups[0].replace(" ", "")  # Remove spaces from card number
                    month = groups[1]
                    year = groups[2]
                    cvv = groups[3]
                    
                    # Handle 2-digit year
                    if len(year) == 2:
                        year = f"20{year}" if int(year) < 50 else f"19{year}"
                    
                    return f"{card}|{month}|{year}|{cvv}"
        
        return None

    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save file and wait for /fchk command"""
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        try:
            file = await update.message.document.get_file()
            filename = f"combos_{user_id}_{datetime.now().timestamp()}.txt"
            await file.download_to_drive(filename)
            
            # Store file reference for this user
            self.user_files[user_id] = filename
            
            await update.message.reply_text(
                "╔═══════════════════════════════════╗\n"
                "║      ✅ 𝗙𝗜𝗟𝗘 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗 ✅          ║\n"
                "╠═══════════════════════════════════╣\n"
                "║  📌 𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝘁𝗵𝗶𝘀 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘄𝗶𝘁𝗵:\n"
                "║  ├─ /fchk   - 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵\n"
                "║  ├─ /msc    - 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲\n"
                "║  ├─ /mrzp   - 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆\n"
                "║  ├─ /ashtxt - 𝗦𝗵𝗼𝗽𝗶𝗳𝘆\n"
                "║  └─ /mbc    - 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲\n"
                "╠═══════════════════════════════════╣\n"
                "║  💡 𝗨𝘀𝗲 . 𝗼𝗿 / 𝗳𝗼𝗿 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀\n"
                "╚═══════════════════════════════════╝"
            )
        except Exception as e:
            logger.error(f"File error: {str(e)}")
            await update.message.reply_text("❌ File processing failed!")

    async def fchk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check cards from a file (must reply to file message)"""
        user_id = update.effective_user.id
        
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        # Check if message is a reply
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐀 𝐅𝐢𝐥𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐖𝐢𝐭𝐡 /fchk\n\n"
                "📁 𝐇𝐨𝐰 𝐓𝐨 𝐔𝐬𝐞:\n"
                "1. Upload your combo file\n"
                "2. Reply to that file message with /fchk"
            )
            return

        replied_message = update.message.reply_to_message
        
        # Check if user has a file stored or if replied message contains a file
        filename = None
        if user_id in self.user_files:
            filename = self.user_files[user_id]
            # Verify file exists
            if not os.path.exists(filename):
                del self.user_files[user_id]
                filename = None
        
        # If no stored file, check if replied message has a document
        if not filename and replied_message.document:
            try:
                file = await replied_message.document.get_file()
                filename = f"combos_{user_id}_{datetime.now().timestamp()}.txt"
                await file.download_to_drive(filename)
            except Exception as e:
                logger.error(f"File download error: {str(e)}")
                await update.message.reply_text("❌ Failed to download file!")
                return
        
        if not filename:
            await update.message.reply_text("❌ No file found! Please upload a file first.")
            return

        if user_id in self.active_tasks:
            await update.message.reply_text("⚠️ Existing process found! Use /stop to cancel")
            return

        # Reset stop flag for this user
        self.stop_flags[user_id] = False
        
        await self.initialize_user_stats(user_id)
        user_semaphore = self.get_user_semaphore(user_id)
        
        # Send initial status message with inline buttons (like gate2)
        started_msg = self.stripe_processor.format_mass_check_started()
        keyboard = [
            [InlineKeyboardButton("𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅ 0", callback_data=f'g1stat_approved_{user_id}')],
            [InlineKeyboardButton("𝟑𝗗𝗦 🔐 0", callback_data=f'g1stat_3ds_{user_id}')],
            [InlineKeyboardButton("𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ 0", callback_data=f'g1stat_declined_{user_id}')],
            [InlineKeyboardButton("𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 Starting...", callback_data=f'g1stat_response_{user_id}')],
            [InlineKeyboardButton("𝗧𝗼𝘁𝗮𝗹 𝗖𝗖 💳 0/0", callback_data=f'g1stat_total_{user_id}')],
            [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g1stop_{user_id}')]
        ]
        status_message = await update.message.reply_text(
            started_msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        self.gate1_status_messages[user_id] = status_message
        
        self.active_tasks[user_id] = asyncio.create_task(
            self.process_combos(user_id, filename, update, user_semaphore, status_message)
        )

    async def chk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check single card or extract from replied message"""
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        await self.initialize_user_stats(user_id)

        combo = None
        extracted_from_reply = False
        
        # Case 1: Check if user provided card as argument
        if context.args:
            combo = context.args[0]
        
        # Case 2: Check if message is a reply to another message
        elif update.message.reply_to_message:
            replied_message = update.message.reply_to_message
            # Try to extract card from replied message text
            if replied_message.text:
                combo = self.extract_card_from_text(replied_message.text)
                if combo:
                    extracted_from_reply = True
                else:
                    # Also check caption if it's a caption
                    if replied_message.caption:
                        combo = self.extract_card_from_text(replied_message.caption)
                        if combo:
                            extracted_from_reply = True
            
            if not combo:
                await update.message.reply_text(
                    "❌ 𝐍𝐨 𝐂𝐚𝐫𝐝 𝐅𝐨𝐮𝐧𝐝 𝐈𝐧 𝐑𝐞𝐩𝐥𝐢𝐞𝐝 𝐌𝐞𝐬𝐬𝐚𝐠𝐞!\n\n"
                    "📌 𝐏𝐥𝐞𝐚𝐬𝐞 𝐒𝐞𝐧𝐝 𝐂𝐚𝐫𝐝 𝐈𝐧 𝐓𝐡𝐢𝐬 𝐅𝐨𝐫𝐦𝐚𝐭:\n"
                    "• 4111111111111111|12|2025|123\n"
                    "• 4111111111111111|12|25|123\n"
                    "• 4111111111111111|12|2025|123|John Doe"
                )
                return
        
        # Case 3: No arguments and not a reply
        else:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐏𝐫𝐨𝐯𝐢𝐝𝐞 𝐀 𝐂𝐚𝐫𝐝 𝐎𝐫 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐀 𝐌𝐞𝐬𝐬𝐚𝐠𝐞!\n\n"
                "📌 𝐅𝐨𝐫𝐦𝐚𝐭𝐬:\n"
                "1. /chk 4111111111111111|12|2025|123\n"
                "2. Reply to any message containing card with /chk\n\n"
                "✅ 𝐄𝐱𝐚𝐦𝐩𝐥𝐞𝐬 𝐈 𝐂𝐚𝐧 𝐄𝐱𝐭𝐫𝐚𝐜𝐭:\n"
                "• 𝗖𝗖 : 5487426756956890|07|2030|092\n"
                "• Status: Approved ✅ Card: 4111111111111111|12|25|123\n"
                "• Any message with card pattern"
            )
            return

        # Validate card format
        if not combo or len(combo.split("|")) < 4:
            await update.message.reply_text(
                "❌ Invalid card format!\n\n"
                "✅ 𝐂𝐨𝐫𝐫𝐞𝐜𝐭 𝐅𝐨𝐫𝐦𝐚𝐭𝐬:\n"
                "• 4111111111111111|12|2025|123\n"
                "• 4111111111111111|12|25|123\n"
                "• 4111111111111111|12|2025|123|John Doe"
            )
            return

        wait_msg = await update.message.reply_text("𝗣𝗹𝗲𝗮𝘀𝗲 𝗪𝗮𝗶𝘁...𝗪𝗵𝗶𝗹𝗲 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗖𝗮𝗿𝗱 💳")

        try:
            user_semaphore = self.get_user_semaphore(user_id)
            result, status, error_message = await self.process_line(user_id, combo, user_semaphore, update, is_single_check=True)
            
            # Delete the wait message
            try:
                await wait_msg.delete()
            except:
                pass
            
            if result:
                bin_info = await self.stripe_processor.fetch_bin_info(combo[:6])
                check_time = random.uniform(3.0, 10.0)
                
                if status == "3d_secure":
                    await self.send_3d_secure_message(update, combo, bin_info, check_time, update.effective_user, error_message)
                else:
                    await self.send_approval(update, combo, bin_info, check_time, update.effective_user, error_message)
            else:
                bin_info = await self.stripe_processor.fetch_bin_info(combo[:6])
                check_time = random.uniform(3.0, 10.0)
                await self.send_declined_message(update, combo, bin_info, check_time, error_message, update.effective_user)
        except Exception as e:
            try:
                await wait_msg.delete()
            except:
                pass
            await update.message.reply_text(f"⚠️ Check failed: {str(e)}")

    async def process_combos(self, user_id, filename, update, user_semaphore, status_message=None):
        """Process multiple combos from a file with stop functionality - 5 cards at a time with 70s cooldown"""
        try:
            with open(filename, 'r') as f:
                combos = []
                for line in f:
                    line = line.strip()
                    if line:
                        # Try to extract card from each line (supports various formats)
                        card = self.extract_card_from_text(line)
                        if card:
                            combos.append(card)
                        else:
                            # If line already in correct format, use it
                            if len(line.split("|")) >= 4:
                                combos.append(line)
                
                if not combos:
                    await update.message.reply_text("❌ No valid cards found in file!")
                    return
                
                self.user_stats[user_id]['total'] = len(combos)
                self.user_stats[user_id]['approved_ccs'] = []
                
                batch_size = 5  # Check 5 cards at once
                cooldown_seconds = 70  # 70 second cooldown after each batch
                
                # Process in batches of 5
                for batch_start in range(0, len(combos), batch_size):
                    # Check stop flag before starting batch
                    if self.stop_flags.get(user_id, False):
                        break
                    
                    batch_end = min(batch_start + batch_size, len(combos))
                    batch = combos[batch_start:batch_end]
                    
                    # Create tasks for this batch
                    tasks = []
                    for combo in batch:
                        if self.stop_flags.get(user_id, False):
                            break
                        task = asyncio.create_task(
                            self.process_line_with_stop_check(user_id, combo, user_semaphore, update, is_single_check=False)
                        )
                        tasks.append(task)
                    
                    # Process batch tasks
                    for future in asyncio.as_completed(tasks):
                        if self.stop_flags.get(user_id, False):
                            for task in tasks:
                                if not task.done():
                                    task.cancel()
                            break
                        
                        try:
                            result, status, error_message = await future
                            self.user_stats[user_id]['checked'] += 1
                            
                            # Store the last response for the Response button
                            if error_message:
                                self.user_stats[user_id]['last_response'] = error_message[:50]
                            elif status:
                                self.user_stats[user_id]['last_response'] = status[:50]
                            
                            if result:
                                self.user_stats[user_id]['approved_ccs'].append(result)
                                bin_info = await self.stripe_processor.fetch_bin_info(result[:6])
                                check_time = random.uniform(3.0, 10.0)
                                
                                if status == "3d_secure":
                                    self.user_stats[user_id]['3ds'] += 1
                                    await self.send_3d_secure_message(update, result, bin_info, check_time, update.effective_user, error_message)
                                else:
                                    self.user_stats[user_id]['approved'] += 1
                                    await self.send_approval(update, result, bin_info, check_time, update.effective_user, error_message)
                            else:
                                self.user_stats[user_id]['declined'] += 1
                            
                            # Update inline buttons after each card
                            if status_message:
                                await self.update_gate1_status_buttons(user_id, status_message)
                                
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            logger.error(f"Task error: {str(e)}")
                            continue
                    
                    # 70 second cooldown after each batch (if not stopped and more cards remain)
                    if not self.stop_flags.get(user_id, False) and batch_end < len(combos):
                        await update.message.reply_text(
                            f"⏳ 𝗕𝗮𝘁𝗰𝗵 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲! 𝗖𝗵𝗲𝗰𝗸𝗲𝗱: {self.user_stats[user_id]['checked']}/{self.user_stats[user_id]['total']}\n"
                            f"⏱️ 𝗖𝗼𝗼𝗹𝗱𝗼𝘄𝗻: 70 𝘀𝗲𝗰𝗼𝗻𝗱𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗯𝗮𝘁𝗰𝗵..."
                        )
                        await asyncio.sleep(cooldown_seconds)

                # Only send final report if not stopped
                if not self.stop_flags.get(user_id, False) and self.user_stats[user_id]['checked'] > 0:
                    await self.send_report(user_id, update)
                elif self.stop_flags.get(user_id, False):
                    await update.message.reply_text("⏹️ Process stopped successfully!")
                    
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            await self.send_message(update, f"❌ Processing failed: {str(e)}")
        finally:
            # Cleanup
            if os.path.exists(filename):
                os.remove(filename)
            if user_id in self.user_files:
                del self.user_files[user_id]
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            if user_id in self.stop_flags:
                del self.stop_flags[user_id]
            self.cleanup_user_semaphore(user_id)

    async def process_line_with_stop_check(self, user_id, combo, semaphore, update, is_single_check=False):
        """Process a single card with stop flag check"""
        # Check stop flag before processing
        if self.stop_flags.get(user_id, False):
            raise asyncio.CancelledError("Process stopped by user")
        
        return await self.process_line(user_id, combo, semaphore, update, is_single_check)

    async def process_line(self, user_id, combo, semaphore, update, is_single_check=False):
        """Process a single card line using the Stripe processor"""
        # Check stop flag
        if self.stop_flags.get(user_id, False):
            raise asyncio.CancelledError("Process stopped by user")
        
        start_time = datetime.now()
        
        async with semaphore:
            # Check stop flag again before actual processing
            if self.stop_flags.get(user_id, False):
                raise asyncio.CancelledError("Process stopped by user")
                
            result, status, error_message = await self.stripe_processor.process_stripe_payment(combo)
            check_time = (datetime.now() - start_time).total_seconds()
            
            if is_single_check:
                return result, status, error_message
            
            return result, status, error_message

    async def send_approval(self, update, combo, bin_info, check_time, user, response=None):
        message = await self.stripe_processor.format_approval_message(combo, bin_info, check_time, user, response)
        try:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 View Stats", callback_data='stats'),
                     InlineKeyboardButton("🛑 Stop Check", callback_data='cancel')]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to send approval: {str(e)}")

    async def send_3d_secure_message(self, update, combo, bin_info, check_time, user, response=None):
        message = await self.stripe_processor.format_3d_secure_message(combo, bin_info, check_time, user, response)
        try:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 View Stats", callback_data='stats'),
                     InlineKeyboardButton("🛑 Stop Check", callback_data='cancel')]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to send 3D secure message: {str(e)}")

    async def send_declined_message(self, update, combo, bin_info, check_time, error_message, user):
        message = await self.stripe_processor.format_declined_message(combo, bin_info, check_time, error_message, user)
        try:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 View Stats", callback_data='stats'),
                     InlineKeyboardButton("🛑 Stop Check", callback_data='cancel')]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to send declined message: {str(e)}")

    async def send_progress_update(self, user_id, update):
        stats = self.user_stats[user_id]
        elapsed = datetime.now() - stats['start_time']
        checked = stats['checked']
        total = stats['total']
        progress_pct = (checked / total * 100) if total > 0 else 0
        bar_filled = int(progress_pct / 10)
        progress_bar = "█" * bar_filled + "░" * (10 - bar_filled)
        
        progress = f"""╔═══════════════════════════════╗
       TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 ⚡ 𝗟𝗜𝗩𝗘
╚═══════════════════════════════╝

┌────────「 📊 𝗣𝗥𝗢𝗚𝗥𝗘𝗦𝗦 」────────┐
│ [{progress_bar}] <code>{progress_pct:.1f}%</code>
│ 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 ⌁ <code>{checked}/{total}</code>
└────────────────────────────────────┘

┌────────「 📈 𝗦𝗧𝗔𝗧𝗦 」────────┐
│ ✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ⌁ <code>{stats['approved']}</code>
│ ❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ⌁ <code>{stats['declined']}</code>
│ ⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 ⌁ <code>{elapsed.seconds // 60}m {elapsed.seconds % 60}s</code>
│ ⚡ 𝗦𝗽𝗲𝗲𝗱 ⌁ <code>{checked/elapsed.seconds if elapsed.seconds else 0:.1f} c/s</code>
│ 📊 𝗥𝗮𝘁𝗲 ⌁ <code>{(stats['approved']/checked)*100 if checked > 0 else 0:.1f}%</code>
└────────────────────────────────────┘
    ╰─➤ 🛑 Use <code>/stop</code> to cancel ✿"""
        await self.send_message(update, progress)

    async def generate_hits_file(self, approved_ccs, total_ccs):
        random_number = random.randint(0, 9999)
        filename = f"hits_ogChecker_{random_number:04d}.txt"
        
        header = f"""━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐇𝐈𝐓𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {len(approved_ccs)}
[✪] 𝐓𝐨𝐭𝐚𝐥: {total_ccs}
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @trial9pm ⚡😈
━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━
𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐇𝐈𝐓𝐒
━━━━━━━━━━━━━━━━━━━━━━
"""
        
        cc_entries = "\n".join([f"Approved ✅ {cc}" for cc in approved_ccs])
        full_content = header + cc_entries
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(full_content)
        
        return filename

    async def send_report(self, user_id, update):
        stats = self.user_stats[user_id]
        elapsed = datetime.now() - stats['start_time']
        checked = stats['checked']
        report = f"""╔═══════════════════════════════╗
       TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 🎯 𝗥𝗘𝗦𝗨𝗟𝗧𝗦
╚═══════════════════════════════╝

┌────────「 📊 𝗦𝗨𝗠𝗠𝗔𝗥𝗬 」────────┐
│ ✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ⌁ <code>{stats['approved']}</code>
│ ❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ⌁ <code>{stats['declined']}</code>
│ 📁 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 ⌁ <code>{checked}</code>
│ 📋 𝗧𝗼𝘁𝗮𝗹 ⌁ <code>{stats['total']}</code>
└────────────────────────────────────┘

┌────────「 ⚡ 𝗣𝗘𝗥𝗙 」────────┐
│ ⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 ⌁ <code>{elapsed.seconds // 60}m {elapsed.seconds % 60}s</code>
│ 🚀 𝗦𝗽𝗲𝗲𝗱 ⌁ <code>{checked/elapsed.seconds if elapsed.seconds else 0:.1f} c/s</code>
│ 📈 𝗦𝘂𝗰𝗰𝗲𝘀𝘀 ⌁ <code>{(stats['approved']/checked)*100 if checked > 0 else 0:.1f}%</code>
└────────────────────────────────────┘
    ╰─➤ <a href="https://t.me/+otlXZvR0ELRiZDRl">TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥</a> ✿"""
        
        # Generate and send hits file if there are approved cards
        if stats['approved_ccs']:
            try:
                hits_file = await self.generate_hits_file(stats['approved_ccs'], stats['checked'])
                await update.message.reply_document(
                    document=open(hits_file, 'rb'),
                    caption="🎯 OG Checker Results Attached"
                )
                os.remove(hits_file)
            except Exception as e:
                logger.error(f"Failed to send hits file: {str(e)}")
        
        await self.send_message(update, report)
        if user_id in self.user_stats:
            del self.user_stats[user_id]

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in self.user_stats:
            await self.send_message(update, "📊 No active checking session. Start one with /fchk")
            return
            
        stats = self.user_stats[user_id]
        elapsed = datetime.now() - stats['start_time']
        message = f"""
━━━━━━━━━━━━━━━━━━━━━━
[⌬] TRIAL 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐒𝐓𝐀𝐓𝐔𝐒 😈⚡
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {stats['approved']}
[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {stats['declined']}
[✪] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {stats['checked']}/{stats['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {stats['checked']/elapsed.seconds if elapsed.seconds else 0:.1f} c/s
[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {(stats['approved']/stats['checked'])*100 if stats['checked'] > 0 else 0:.2f}%
━━━━━━━━━━━━━━━━━━━━━━
[み] 𝐃𝐞𝐯: @trial9pm ⚡😈
━━━━━━━━━━━━━━━━━━━━━━
🛑 Use /stop to cancel"""
        await self.send_message(update, message)

    async def info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot information and features"""
        user = update.effective_user
        user_link = f"tg://user?id={user.id}"
        username = user.username if user.username else user.full_name
        
        proxy_count = len(self.stripe_processor.proxy_pool) if hasattr(self.stripe_processor, 'proxy_pool') else 0
        sites_count = len(get_sites()) if get_sites() else 0
        total_admins = len(self.admin_ids)
        
        is_subscribed = await self.is_user_allowed(user.id)
        sub_status = f"{to_monospace('Active')} ✅" if is_subscribed else f"{to_monospace('Inactive')} ❌"
        
        user_data = self.users_col.find_one({'user_id': str(user.id)})
        if user_data and user_data.get('expires_at'):
            exp_date = to_monospace(user_data['expires_at'].strftime('%Y-%m-%d %H:%M'))
        else:
            exp_date = to_monospace("N/A")
        
        bot_link = "https://t.me/+otlXZvR0ELRiZDRl"
        
        info_message = f"""╔═══════════════════════════╗
       TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 ℹ️ 𝗜𝗡𝗙𝗢
╚═══════════════════════════╝

┌─────────「  𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗨𝗦  」─────────┐
│ 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {to_monospace('Online')} 🟢
│ 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 ⌁ {to_monospace(proxy_count)} {to_monospace('Loaded')}
│ 𝗦𝗶𝘁𝗲𝘀 ⌁ {to_monospace(sites_count)} {to_monospace('Available')}
│ 𝗔𝗱𝗺𝗶𝗻𝘀 ⌁ {to_monospace(total_admins)}
└────────────────────────────────┘

┌────────「  𝗬𝗢𝗨𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘  」────────┐
│ 𝗨𝘀𝗲𝗿 ⌁ <a href="{user_link}">{to_monospace(username)}</a>
│ 𝗜𝗗 ⌁ <code>{user.id}</code>
│ 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 ⌁ {sub_status}
│ 𝗘𝘅𝗽𝗶𝗿𝗲𝘀 ⌁ {exp_date}
└────────────────────────────────┘

┌────────「  𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗚𝗔𝗧𝗘𝗦  」────────┐
│ 🔐 {to_monospace('Stripe Auth')} ⌁ /chk
│ 💳 {to_monospace('Stripe Charge $5')} ⌁ /sc
│ 💰 {to_monospace('Razorpay')} ₹1 ⌁ /rzp
│ 🛒 {to_monospace('Shopify Auto')} ⌁ /ash
│ 🌳 {to_monospace('Braintree $1')} ⌁ /bc
└────────────────────────────────┘

┌─────────「  𝗧𝗢𝗢𝗟𝗦  」─────────┐
│ 🧹 {to_monospace('Cleaner')} ⌁ /clean
│ 💳 {to_monospace('CC Extract')} ⌁ /ccn
│ 📧 {to_monospace('ULP Extract')} ⌁ /ulp
│ 📄 {to_monospace('To TXT')} ⌁ /txt
│ ✂️ {to_monospace('Split File')} ⌁ /split
│ 🔢 {to_monospace('BIN Filter')} ⌁ /bin
│ 📊 {to_monospace('Sort Cards')} ⌁ /sort
└────────────────────────────────┘
  ╰─➤ <a href="{bot_link}">TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥</a> ✿"""
        
        await self.send_message(update, info_message)

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop the current checking process for the user"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        async def send_reply(text):
            try:
                if update.message:
                    await update.message.reply_text(text)
                elif update.callback_query:
                    await context.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Failed to send reply: {e}")
        
        async def send_document(doc, caption):
            try:
                if update.message:
                    await update.message.reply_document(document=doc, caption=caption)
                elif update.callback_query:
                    await context.bot.send_document(chat_id=chat_id, document=doc, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send document: {e}")
        
        if user_id in self.active_tasks:
            self.stop_flags[user_id] = True
            
            task = self.active_tasks[user_id]
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            await send_reply("⏹️ Process stopped successfully!")
            
            if user_id in self.user_stats:
                if self.user_stats[user_id]['checked'] > 0:
                    elapsed = datetime.now() - self.user_stats[user_id]['start_time']
                    partial_report = f"""
⏹️ Process Stopped by User

━━━━━━━━━━━━━━━━━━━━━━
[⌬] 𝐏𝐀𝐑𝐓𝐈𝐀𝐋 𝐑𝐄𝐒𝐔𝐋𝐓𝐒
━━━━━━━━━━━━━━━━━━━━━━
[✪] 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝: {self.user_stats[user_id]['approved']}
[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {self.user_stats[user_id]['declined']}
[✪] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {self.user_stats[user_id]['checked']}/{self.user_stats[user_id]['total']}
[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
━━━━━━━━━━━━━━━━━━━━━━
"""
                    await send_reply(partial_report)
                
                if self.user_stats[user_id]['approved_ccs']:
                    try:
                        hits_file = await self.generate_hits_file(
                            self.user_stats[user_id]['approved_ccs'], 
                            self.user_stats[user_id]['checked']
                        )
                        await send_document(open(hits_file, 'rb'), "🎯 Partial Results (Stopped)")
                        os.remove(hits_file)
                    except Exception as e:
                        logger.error(f"Failed to send partial hits file: {str(e)}")
                
                del self.user_stats[user_id]
            
            if user_id in self.user_files:
                filename = self.user_files[user_id]
                if os.path.exists(filename):
                    os.remove(filename)
                del self.user_files[user_id]
            
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            
            self.cleanup_user_semaphore(user_id)
            
            if user_id in self.stop_flags:
                del self.stop_flags[user_id]
                
        else:
            await send_reply("⚠️ No active checking process to stop!")

    async def send_message(self, update, text):
        try:
            await update.message.reply_text(text, parse_mode='HTML')
        except:
            try:
                await update.callback_query.message.reply_text(text, parse_mode='HTML')
            except:
                logger.error("Failed to send message")

    async def sc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        combo = None
        if context.args:
            combo = context.args[0]
        elif update.message.reply_to_message and update.message.reply_to_message.text:
            combo = self.extract_card_from_text(update.message.reply_to_message.text)
        
        if not combo or len(combo.split("|")) < 4:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐏𝐫𝐨𝐯𝐢𝐝𝐞 𝐀 𝐂𝐚𝐫𝐝!\n\n"
                "📌 𝐅𝐨𝐫𝐦𝐚𝐭: /sc 4111111111111111|12|2025|123\n"
                "𝐎𝐫 𝐫𝐞𝐩𝐥𝐲 𝐭𝐨 𝐚 𝐦𝐞𝐬𝐬𝐚𝐠𝐞 𝐰𝐢𝐭𝐡 𝐜𝐚𝐫𝐝"
            )
            return

        await update.message.reply_text("🔍 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗖𝗮𝗿𝗱 𝘄𝗶𝘁𝗵 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲 $5...")
        
        try:
            result = await self.gate2_processor.process_card(combo)
            bin_info = await self.gate2_processor.fetch_bin_info(combo[:6])
            check_time = result.get('check_time', 0)
            
            if result['status'] == 'charged':
                message = self.gate2_processor.format_charged_message(
                    combo, bin_info, check_time, update.effective_user, result['raw_response']
                )
            elif result['status'] == '3ds':
                message = self.gate2_processor.format_3ds_message(
                    combo, bin_info, check_time, update.effective_user, result['raw_response']
                )
            else:
                message = self.gate2_processor.format_declined_message(
                    combo, bin_info, check_time, update.effective_user, result['raw_response']
                )
            
            await update.message.reply_text(message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"SC command error: {str(e)}")
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    async def msc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        if not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐀 𝐅𝐢𝐥𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐖𝐢𝐭𝐡 /msc\n\n"
                "📁 𝐇𝐨𝐰 𝐓𝐨 𝐔𝐬𝐞:\n"
                "1. Upload your combo file\n"
                "2. Reply to that file message with /msc"
            )
            return

        replied_message = update.message.reply_to_message
        filename = None
        
        if user_id in self.user_files:
            filename = self.user_files[user_id]
            if not os.path.exists(filename):
                del self.user_files[user_id]
                filename = None
        
        if not filename and replied_message.document:
            try:
                file = await replied_message.document.get_file()
                filename = f"gate2_combos_{user_id}_{datetime.now().timestamp()}.txt"
                await file.download_to_drive(filename)
            except Exception as e:
                logger.error(f"File download error: {str(e)}")
                await update.message.reply_text("❌ Failed to download file!")
                return
        
        if not filename:
            await update.message.reply_text("❌ No file found! Please upload a file first.")
            return

        if user_id in self.gate2_active_tasks:
            await update.message.reply_text("⚠️ Existing process found! Use /stop to cancel")
            return

        self.gate2_stop_flags[user_id] = False
        self.gate2_stats[user_id] = {
            'total': 0,
            'charged': 0,
            'declined': 0,
            '3ds': 0,
            'checked': 0,
            'last_response': 'Starting...',
            'start_time': datetime.now()
        }
        
        started_msg = self.gate2_processor.format_mass_check_started()
        keyboard = [
            [InlineKeyboardButton("𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥 0", callback_data=f'g2stat_charged_{user_id}')],
            [InlineKeyboardButton("𝟑𝗗𝗦 🔐 0", callback_data=f'g2stat_3ds_{user_id}')],
            [InlineKeyboardButton("𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ 0", callback_data=f'g2stat_declined_{user_id}')],
            [InlineKeyboardButton("𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 Starting...", callback_data=f'g2stat_response_{user_id}')],
            [InlineKeyboardButton("𝗧𝗼𝘁𝗮𝗹 𝗖𝗖 💳 0/0", callback_data=f'g2stat_total_{user_id}')],
            [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g2stop_{user_id}')]
        ]
        status_message = await update.message.reply_text(
            started_msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        self.gate2_status_messages[user_id] = status_message
        
        self.gate2_active_tasks[user_id] = asyncio.create_task(
            self.process_gate2_mass_check(user_id, filename, update, status_message)
        )

    async def process_gate2_mass_check(self, user_id, filename, update, status_message):
        try:
            with open(filename, 'r') as f:
                combos = []
                for line in f:
                    line = line.strip()
                    if line:
                        card = self.extract_card_from_text(line)
                        if card:
                            combos.append(card)
                        elif len(line.split("|")) >= 4:
                            combos.append(line)
            
            if not combos:
                await update.message.reply_text("❌ No valid cards found in file!")
                return
            
            self.gate2_stats[user_id]['total'] = len(combos)
            
            for i, combo in enumerate(combos):
                if self.gate2_stop_flags.get(user_id, False):
                    break
                
                result = await self.gate2_processor.process_card(combo)
                self.gate2_stats[user_id]['checked'] += 1
                self.gate2_stats[user_id]['last_response'] = result.get('raw_response', 'N/A')[:30]
                
                bin_info = await self.gate2_processor.fetch_bin_info(combo[:6])
                
                if result['status'] == 'charged':
                    self.gate2_stats[user_id]['charged'] += 1
                    message = self.gate2_processor.format_charged_message(
                        combo, bin_info, result.get('check_time', 0), 
                        update.effective_user, result['raw_response']
                    )
                    await update.message.reply_text(message, parse_mode='HTML')
                elif result['status'] == '3ds':
                    self.gate2_stats[user_id]['3ds'] += 1
                    message = self.gate2_processor.format_3ds_message(
                        combo, bin_info, result.get('check_time', 0),
                        update.effective_user, result['raw_response']
                    )
                    await update.message.reply_text(message, parse_mode='HTML')
                else:
                    self.gate2_stats[user_id]['declined'] += 1
                
                await self.update_gate2_status_buttons(user_id, status_message)
                
                if i < len(combos) - 1 and not self.gate2_stop_flags.get(user_id, False):
                    await asyncio.sleep(10)
            
            if not self.gate2_stop_flags.get(user_id, False):
                stats = self.gate2_stats[user_id]
                elapsed = datetime.now() - stats['start_time']
                report = f"""━━━━━━━━━━━━━━━━━━━━━━
TRIAL 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 ✿
━━━━━━━━━━━━━━━━━━━━━━
𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥: {stats['charged']}
𝟑𝗗𝗦 🔐: {stats['3ds']}
𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌: {stats['declined']}
𝗧𝗼𝘁𝗮𝗹 💳: {stats['checked']}/{stats['total']}
𝗧𝗶𝗺𝗲 ⏱️: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
━━━━━━━━━━━━━━━━━━━━━━"""
                await update.message.reply_text(report)
                
        except Exception as e:
            logger.error(f"Gate2 mass check error: {str(e)}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            if user_id in self.user_files:
                del self.user_files[user_id]
            if user_id in self.gate2_active_tasks:
                del self.gate2_active_tasks[user_id]
            if user_id in self.gate2_stop_flags:
                del self.gate2_stop_flags[user_id]
            if user_id in self.gate2_stats:
                del self.gate2_stats[user_id]

    async def update_gate2_status_buttons(self, user_id, status_message):
        try:
            stats = self.gate2_stats.get(user_id, {})
            keyboard = [
                [InlineKeyboardButton(f"𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥 {stats.get('charged', 0)}", callback_data=f'g2stat_charged_{user_id}')],
                [InlineKeyboardButton(f"𝟑𝗗𝗦 🔐 {stats.get('3ds', 0)}", callback_data=f'g2stat_3ds_{user_id}')],
                [InlineKeyboardButton(f"𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ {stats.get('declined', 0)}", callback_data=f'g2stat_declined_{user_id}')],
                [InlineKeyboardButton(f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 {stats.get('last_response', 'N/A')[:25]}", callback_data=f'g2stat_response_{user_id}')],
                [InlineKeyboardButton(f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗖 💳 {stats.get('checked', 0)}/{stats.get('total', 0)}", callback_data=f'g2stat_total_{user_id}')],
                [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g2stop_{user_id}')]
            ]
            await status_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Failed to update status buttons: {str(e)}")

    async def update_gate1_status_buttons(self, user_id, status_message):
        """Update Gate 1 inline buttons with current stats"""
        try:
            stats = self.user_stats.get(user_id, {})
            keyboard = [
                [InlineKeyboardButton(f"𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅ {stats.get('approved', 0)}", callback_data=f'g1stat_approved_{user_id}')],
                [InlineKeyboardButton(f"𝟑𝗗𝗦 🔐 {stats.get('3ds', 0)}", callback_data=f'g1stat_3ds_{user_id}')],
                [InlineKeyboardButton(f"𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ {stats.get('declined', 0)}", callback_data=f'g1stat_declined_{user_id}')],
                [InlineKeyboardButton(f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 {stats.get('last_response', 'N/A')[:25]}", callback_data=f'g1stat_response_{user_id}')],
                [InlineKeyboardButton(f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗖 💳 {stats.get('checked', 0)}/{stats.get('total', 0)}", callback_data=f'g1stat_total_{user_id}')],
                [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g1stop_{user_id}')]
            ]
            await status_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Failed to update gate1 status buttons: {str(e)}")

    async def rzp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check single card with Razorpay Gate 3"""
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        combo = None
        if context.args:
            combo = context.args[0]
        elif update.message.reply_to_message and update.message.reply_to_message.text:
            combo = self.extract_card_from_text(update.message.reply_to_message.text)
        
        if not combo or len(combo.split("|")) < 4:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐏𝐫𝐨𝐯𝐢𝐝𝐞 𝐀 𝐂𝐚𝐫𝐝!\n\n"
                "📌 𝐅𝐨𝐫𝐦𝐚𝐭: /rzp 4111111111111111|12|2025|123\n"
                "𝐎𝐫 𝐫𝐞𝐩𝐥𝐲 𝐭𝐨 𝐚 𝐦𝐞𝐬𝐬𝐚𝐠𝐞 𝐰𝐢𝐭𝐡 𝐜𝐚𝐫𝐝"
            )
            return

        await update.message.reply_text("🔍 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗖𝗮𝗿𝗱 𝘄𝗶𝘁𝗵 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 ₹1...")
        
        try:
            result = await self.gate3_processor.process_card(combo)
            bin_info = await self.gate3_processor.fetch_bin_info(combo[:6])
            check_time = result.get('check_time', 0)
            
            if result['status'] == 'charged':
                message = self.gate3_processor.format_charged_message(
                    combo, bin_info, check_time, update.effective_user, result['raw_response']
                )
            elif result['status'] == '3ds':
                message = self.gate3_processor.format_3ds_message(
                    combo, bin_info, check_time, update.effective_user, result['raw_response']
                )
            else:
                message = self.gate3_processor.format_declined_message(
                    combo, bin_info, check_time, update.effective_user, result['raw_response']
                )
            
            await update.message.reply_text(message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"RZP command error: {str(e)}")
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    async def mrzp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mass check cards with Razorpay Gate 3 (20 second delay)"""
        user_id = update.effective_user.id
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ Authorization required!")
            return

        if not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐀 𝐅𝐢𝐥𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐖𝐢𝐭𝐡 /mrzp\n\n"
                "📁 𝐇𝐨𝐰 𝐓𝐨 𝐔𝐬𝐞:\n"
                "1. Upload your combo file\n"
                "2. Reply to that file message with /mrzp"
            )
            return

        replied_message = update.message.reply_to_message
        filename = None
        
        if user_id in self.user_files:
            filename = self.user_files[user_id]
            if not os.path.exists(filename):
                del self.user_files[user_id]
                filename = None
        
        if not filename and replied_message.document:
            try:
                file = await replied_message.document.get_file()
                filename = f"gate3_combos_{user_id}_{datetime.now().timestamp()}.txt"
                await file.download_to_drive(filename)
            except Exception as e:
                logger.error(f"File download error: {str(e)}")
                await update.message.reply_text("❌ Failed to download file!")
                return
        
        if not filename:
            await update.message.reply_text("❌ No file found! Please upload a file first.")
            return

        if user_id in self.gate3_active_tasks:
            await update.message.reply_text("⚠️ Existing process found! Use /stop to cancel")
            return

        if user_id in self.gate3_last_completion:
            elapsed = (datetime.now() - self.gate3_last_completion[user_id]).total_seconds()
            remaining = self.gate3_cooldown_seconds - elapsed
            if remaining > 0:
                await update.message.reply_text(
                    f"⏳ 𝗖𝗼𝗼𝗹𝗱𝗼𝘄𝗻 𝗔𝗰𝘁𝗶𝘃𝗲!\n\n"
                    f"𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁 {int(remaining)} 𝘀𝗲𝗰𝗼𝗻𝗱𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝘀𝘁𝗮𝗿𝘁𝗶𝗻𝗴 𝗮𝗻𝗼𝘁𝗵𝗲𝗿 𝗺𝗮𝘀𝘀 𝗰𝗵𝗲𝗰𝗸."
                )
                return

        self.gate3_stop_flags[user_id] = False
        self.gate3_stats[user_id] = {
            'total': 0,
            'charged': 0,
            'declined': 0,
            '3ds': 0,
            'checked': 0,
            'last_response': 'Starting...',
            'start_time': datetime.now()
        }
        
        started_msg = """━━━━━━━━━━━━━━━━━━━━━━
TRIAL 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞 𝗦𝗧𝗔𝗥𝗧𝗘𝗗 ✿
𝗚𝗮𝘁𝗲: 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 ₹𝟭
━━━━━━━━━━━━━━━━━━━━━━"""
        keyboard = [
            [InlineKeyboardButton("𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥 0", callback_data=f'g3stat_charged_{user_id}')],
            [InlineKeyboardButton("𝟑𝗗𝗦 🔐 0", callback_data=f'g3stat_3ds_{user_id}')],
            [InlineKeyboardButton("𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ 0", callback_data=f'g3stat_declined_{user_id}')],
            [InlineKeyboardButton("𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 Starting...", callback_data=f'g3stat_response_{user_id}')],
            [InlineKeyboardButton("𝗧𝗼𝘁𝗮𝗹 𝗖𝗖 💳 0/0", callback_data=f'g3stat_total_{user_id}')],
            [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g3stop_{user_id}')]
        ]
        status_message = await update.message.reply_text(
            started_msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        self.gate3_status_messages[user_id] = status_message
        
        self.gate3_active_tasks[user_id] = asyncio.create_task(
            self.process_gate3_mass_check(user_id, filename, update, status_message)
        )

    async def process_gate3_mass_check(self, user_id, filename, update, status_message):
        """Process mass check for Gate 3 Razorpay with 20 second delay"""
        try:
            with open(filename, 'r') as f:
                combos = []
                for line in f:
                    line = line.strip()
                    if line:
                        card = self.extract_card_from_text(line)
                        if card:
                            combos.append(card)
                        elif len(line.split("|")) >= 4:
                            combos.append(line)
            
            if not combos:
                await update.message.reply_text("❌ No valid cards found in file!")
                return
            
            original_count = len(combos)
            if len(combos) > self.gate3_max_cards:
                combos = combos[:self.gate3_max_cards]
                await update.message.reply_text(
                    f"⚠️ 𝗙𝗶𝗹𝗲 𝗰𝗼𝗻𝘁𝗮𝗶𝗻𝘀 {original_count} 𝗰𝗮𝗿𝗱𝘀.\n"
                    f"𝗢𝗻𝗹𝘆 𝗳𝗶𝗿𝘀𝘁 {self.gate3_max_cards} 𝗰𝗮𝗿𝗱𝘀 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗰𝗵𝗲𝗰𝗸𝗲𝗱."
                )
            
            self.gate3_stats[user_id]['total'] = len(combos)
            
            for i, combo in enumerate(combos):
                if self.gate3_stop_flags.get(user_id, False):
                    break
                
                result = await self.gate3_processor.process_card(combo)
                self.gate3_stats[user_id]['checked'] += 1
                self.gate3_stats[user_id]['last_response'] = result.get('raw_response', 'N/A')[:30]
                
                bin_info = await self.gate3_processor.fetch_bin_info(combo[:6])
                
                if result['status'] == 'charged':
                    self.gate3_stats[user_id]['charged'] += 1
                    message = self.gate3_processor.format_charged_message(
                        combo, bin_info, result.get('check_time', 0), 
                        update.effective_user, result['raw_response']
                    )
                    await update.message.reply_text(message, parse_mode='HTML')
                elif result['status'] == '3ds':
                    self.gate3_stats[user_id]['3ds'] += 1
                    message = self.gate3_processor.format_3ds_message(
                        combo, bin_info, result.get('check_time', 0),
                        update.effective_user, result['raw_response']
                    )
                    await update.message.reply_text(message, parse_mode='HTML')
                else:
                    self.gate3_stats[user_id]['declined'] += 1
                
                await self.update_gate3_status_buttons(user_id, status_message)
                
                if i < len(combos) - 1 and not self.gate3_stop_flags.get(user_id, False):
                    await asyncio.sleep(20)
            
            self.gate3_last_completion[user_id] = datetime.now()
            
            if not self.gate3_stop_flags.get(user_id, False):
                stats = self.gate3_stats[user_id]
                elapsed = datetime.now() - stats['start_time']
                report = f"""━━━━━━━━━━━━━━━━━━━━━━
TRIAL 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 ✿
𝗚𝗮𝘁𝗲: 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 ₹𝟭
━━━━━━━━━━━━━━━━━━━━━━
𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥: {stats['charged']}
𝟑𝗗𝗦 🔐: {stats['3ds']}
𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌: {stats['declined']}
𝗧𝗼𝘁𝗮𝗹 💳: {stats['checked']}/{stats['total']}
𝗧𝗶𝗺𝗲 ⏱️: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
━━━━━━━━━━━━━━━━━━━━━━
⏳ 𝗖𝗼𝗼𝗹𝗱𝗼𝘄𝗻: 𝟱𝟬 𝘀𝗲𝗰𝗼𝗻𝗱𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗺𝗮𝘀𝘀 𝗰𝗵𝗲𝗰𝗸"""
                await update.message.reply_text(report)
                
        except Exception as e:
            logger.error(f"Gate3 mass check error: {str(e)}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            if user_id in self.user_files:
                del self.user_files[user_id]
            if user_id in self.gate3_active_tasks:
                del self.gate3_active_tasks[user_id]
            if user_id in self.gate3_stop_flags:
                del self.gate3_stop_flags[user_id]
            if user_id in self.gate3_stats:
                del self.gate3_stats[user_id]

    async def update_gate3_status_buttons(self, user_id, status_message):
        """Update Gate 3 inline buttons with current stats"""
        try:
            stats = self.gate3_stats.get(user_id, {})
            keyboard = [
                [InlineKeyboardButton(f"𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥 {stats.get('charged', 0)}", callback_data=f'g3stat_charged_{user_id}')],
                [InlineKeyboardButton(f"𝟑𝗗𝗦 🔐 {stats.get('3ds', 0)}", callback_data=f'g3stat_3ds_{user_id}')],
                [InlineKeyboardButton(f"𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ {stats.get('declined', 0)}", callback_data=f'g3stat_declined_{user_id}')],
                [InlineKeyboardButton(f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 {stats.get('last_response', 'N/A')[:25]}", callback_data=f'g3stat_response_{user_id}')],
                [InlineKeyboardButton(f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗖 💳 {stats.get('checked', 0)}/{stats.get('total', 0)}", callback_data=f'g3stat_total_{user_id}')],
                [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g3stop_{user_id}')]
            ]
            await status_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Failed to update gate3 status buttons: {str(e)}")


    # ===== GATE 4 SHOPIFY COMMANDS =====
    
    async def addsite_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a site to bot or user's site list"""
        user = update.effective_user
        if not await self.is_user_allowed(user.id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Usage: /addsite <site_url>\nExample: /addsite https://example.myshopify.com")
            return
        
        is_admin = user.id == self.admin_id
        sites_added = []
        
        for site in context.args:
            if is_admin:
                if add_site(site, is_bot_site=True):
                    sites_added.append(site)
            else:
                if add_site(site, user_id=user.id, is_bot_site=False):
                    sites_added.append(site)
        
        if sites_added:
            target = "bot list" if is_admin else "your list"
            await update.message.reply_text(f"✅ Added {len(sites_added)} site(s) to {target}!")
        else:
            await update.message.reply_text("❌ Sites already exist or invalid!")
    
    async def rmsite_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a site from bot or user's site list"""
        user = update.effective_user
        if not await self.is_user_allowed(user.id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Usage: /rmsite <site_url>")
            return
        
        is_admin = user.id == self.admin_id
        site = context.args[0]
        
        if is_admin:
            if remove_site(site, is_bot_site=True):
                await update.message.reply_text(f"✅ Removed {site} from bot list!")
            else:
                await update.message.reply_text("❌ Site not found in bot list!")
        else:
            if remove_site(site, user_id=user.id, is_bot_site=False):
                await update.message.reply_text(f"✅ Removed {site} from your list!")
            else:
                await update.message.reply_text("❌ Site not found in your list!")
    
    async def listsite_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List sites - admin sees all, premium sees their own"""
        user = update.effective_user
        if not await self.is_user_allowed(user.id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        is_admin = user.id == self.admin_id
        
        if is_admin:
            sites = get_sites(bot_sites=True)
            if sites:
                site_list = "\n".join([f"• {s}" for s in sites[:50]])
                await update.message.reply_text(f"🛒 𝗕𝗼𝘁 𝗦𝗶𝘁𝗲𝘀 ({len(sites)} total):\n\n{site_list}" + ("\n..." if len(sites) > 50 else ""))
            else:
                await update.message.reply_text("❌ No sites in bot list!")
        else:
            sites = get_sites(user_id=user.id, bot_sites=False)
            if sites:
                site_list = "\n".join([f"• {s}" for s in sites])
                await update.message.reply_text(f"🛒 𝗬𝗼𝘂𝗿 𝗦𝗶𝘁𝗲𝘀:\n\n{site_list}")
            else:
                await update.message.reply_text("❌ You haven't added any sites! Use /addsite to add.")
    
    async def chksite_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if a site is working"""
        user = update.effective_user
        if not await self.is_user_allowed(user.id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Usage: /chksite <site_url>")
            return
        
        site = context.args[0]
        await update.message.reply_text(f"🔄 Checking {site}...")
        
        result = await check_site_shopify(site)
        
        if result['status'] == 'working':
            await update.message.reply_text(f"✅ {site}\n{result['message']}")
        elif result['status'] == 'captcha':
            await update.message.reply_text(f"⚠️ {site}\n{result['message']}")
        else:
            await update.message.reply_text(f"❌ {site}\n{result['message']}")
    
    async def chkaddedsite_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check all added sites and remove non-working ones (except captcha)"""
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        sites = get_sites(bot_sites=True)
        if not sites:
            await update.message.reply_text("❌ No sites added yet!")
            return
        
        status_msg = await update.message.reply_text(f"🔄 Checking {len(sites)} sites...\n\n⏳ Starting...")
        checked = 0
        total = len(sites)
        
        async def site_callback(result):
            nonlocal checked
            checked += 1
            status, site, message = result
            
            if status == "working":
                icon = "✅"
            elif status == "captcha":
                icon = "⚠️"
            else:
                icon = "❌"
            
            try:
                short_site = site[:30] + "..." if len(site) > 30 else site
                await update.message.reply_text(f"{icon} [{checked}/{total}] {short_site}\n{message[:50]}")
            except:
                pass
        
        results = await check_all_sites_shopify(callback=site_callback)
        
        report = f"""━━━━━━━━━━━━━━━━━━━━━━
🛒 𝗦𝗜𝗧𝗘 𝗖𝗛𝗘𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘
━━━━━━━━━━━━━━━━━━━━━━
✅ Working: {len(results['working'])}
⚠️ Captcha (kept): {len(results['captcha'])}
❌ Removed: {len(results['failed'])}
━━━━━━━━━━━━━━━━━━━━━━"""
        
        await update.message.reply_text(report)
    
    async def asm_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add sites from txt file"""
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("⛔ Admin only command!")
            return
        
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text("❌ Reply to a .txt file with /asm")
            return
        
        document = update.message.reply_to_message.document
        if not document.file_name.endswith('.txt'):
            await update.message.reply_text("❌ Please upload a .txt file!")
            return
        
        file = await document.get_file()
        filename = f"/tmp/sites_{user.id}.txt"
        await file.download_to_drive(filename)
        
        added = add_sites_from_file(filename)
        
        if os.path.exists(filename):
            os.remove(filename)
        
        await update.message.reply_text(f"✅ Added {added} new sites to bot list!")
    
    async def ash_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Single card check with Shopify"""
        user = update.effective_user
        if not await self.is_user_allowed(user.id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        card_data = None
        if context.args:
            card_data = ' '.join(context.args)
        elif update.message.reply_to_message:
            card_data = update.message.reply_to_message.text
        
        if not card_data:
            await update.message.reply_text("❌ Usage: /ash cc|mm|yy|cvv")
            return
        
        card_pattern = r'(\d{13,19})[|/](\d{1,2})[|/](\d{2,4})[|/](\d{3,4})'
        match = re.search(card_pattern, card_data)
        
        if not match:
            await update.message.reply_text("❌ Invalid card format! Use: cc|mm|yy|cvv")
            return
        
        cc, mes, ano, cvv = match.groups()
        
        user_sites = get_sites(user_id=user.id, bot_sites=False)
        if user_sites:
            keyboard = [
                [InlineKeyboardButton("🏠 Use My Sites", callback_data=f'g4_use_own_{user.id}')],
                [InlineKeyboardButton("🤖 Use Bot Sites", callback_data=f'g4_use_bot_{user.id}')]
            ]
            choice_msg = await update.message.reply_text(
                "🛒 You have your own sites added.\nWhich sites do you want to use?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await asyncio.sleep(5)
            try:
                await choice_msg.delete()
            except:
                pass
        
        use_user_sites = self.gate4_user_site_choice.get(user.id, False)
        
        await update.message.reply_text(f"🔄 Checking card with Shopify...")
        
        start_time = datetime.now()
        result = await check_card_shopify(cc, mes, ano, cvv, user_id=user.id, use_user_sites=use_user_sites)
        check_time = (datetime.now() - start_time).total_seconds()
        
        bin_info = await self.fetch_bin_info(cc[:6])
        card = f"{cc}|{mes}|{ano}|{cvv}"
        site = result.get('site', 'N/A')
        amount = result.get('amount', 'N/A')
        proxy = result.get('proxy', 'N/A')
        
        if result['status'] == 'charged':
            message = g4_format_charged(card, bin_info, check_time, user, result.get('message', 'Charged'), site, amount, proxy)
        elif result['status'] == 'approved':
            message = g4_format_approved(card, bin_info, check_time, user, result.get('message', 'Approved'), site, amount, proxy)
        else:
            message = g4_format_declined(card, bin_info, check_time, user, result.get('message', 'Declined'), site, amount, proxy)
        
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def bc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Single card check with B3 (Braintree/Brandmark)"""
        user = update.effective_user
        if not await self.is_user_allowed(user.id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        card_data = None
        if context.args:
            card_data = ' '.join(context.args)
        elif update.message.reply_to_message:
            card_data = update.message.reply_to_message.text
        
        if not card_data:
            await update.message.reply_text("❌ Usage: /bc cc|mm|yy|cvv")
            return
        
        card_pattern = r'(\d{13,19})[|/](\d{1,2})[|/](\d{2,4})[|/](\d{3,4})'
        match = re.search(card_pattern, card_data)
        
        if not match:
            await update.message.reply_text("❌ Invalid card format! Use: cc|mm|yy|cvv")
            return
        
        cc, mes, ano, cvv = match.groups()
        
        status_msg = await update.message.reply_text("🔄 𝙱𝟹 𝙶𝚊𝚝𝚎 - Extracting tokens & checking card...")
        
        start_time = datetime.now()
        result = await gate5.check_card(cc, mes, ano, cvv)
        check_time = (datetime.now() - start_time).total_seconds()
        
        bin_info = await self.fetch_bin_info(cc[:6])
        card = f"{cc}|{mes}|{ano}|{cvv}"
        
        bot_link = "https://t.me/+otlXZvR0ELRiZDRl"
        user_link = f"tg://user?id={user.id}"
        username = user.username if user.username else user.first_name
        
        brand = bin_info.get('brand', 'N/A').upper()
        card_type = bin_info.get('type', 'N/A').upper()
        level = bin_info.get('level', 'N/A').upper()
        bank = bin_info.get('bank', 'N/A').upper()
        country = bin_info.get('country', 'N/A').upper()
        country_flag = bin_info.get('flag', '')
        response = result['message']
        
        bin_display = self.stripe_processor.to_monospace(f"{brand} - {card_type} - {level}")
        bank_display = self.stripe_processor.to_monospace(bank)
        country_display = self.stripe_processor.to_monospace(country)
        
        if result['status'] == 'approved':
            status_text = self.stripe_processor.to_monospace('Charged 1$!')
            status_icon = "✅"
        elif result['status'] == 'ccn':
            status_text = self.stripe_processor.to_monospace('CCN Live!')
            status_icon = "🔥"
        elif result['status'] == 'declined':
            status_text = self.stripe_processor.to_monospace('Dead!')
            status_icon = "❌"
        else:
            status_text = self.stripe_processor.to_monospace('Error!')
            status_icon = "⚠️"
        
        message = f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {status_text} {status_icon}
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {self.stripe_processor.to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {self.stripe_processor.to_monospace('B3 Charge 1$')}
<a href="{bot_link}">[⌯]</a> 𝗧𝗶𝗺𝗲 ⌁ {self.stripe_processor.to_monospace(f'{check_time:.2f}')}'s
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{self.stripe_processor.to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""
        
        try:
            await status_msg.delete()
        except:
            pass
        
        await update.message.reply_text(message, parse_mode='HTML')
    
    def format_b3_message(self, card, bin_info, result, user, status):
        bot_link = "https://t.me/+otlXZvR0ELRiZDRl"
        user_link = f"tg://user?id={user.id}"
        username = user.username if user.username else user.first_name
        
        brand = bin_info.get('brand', 'N/A').upper()
        card_type = bin_info.get('type', 'N/A').upper()
        level = bin_info.get('level', 'N/A').upper()
        bank = bin_info.get('bank', 'N/A').upper()
        country = bin_info.get('country', 'N/A').upper()
        country_flag = bin_info.get('flag', '')
        response = result['message']
        
        bin_display = self.stripe_processor.to_monospace(f"{brand} - {card_type} - {level}")
        bank_display = self.stripe_processor.to_monospace(bank)
        country_display = self.stripe_processor.to_monospace(country)
        
        if status == 'approved':
            status_text = self.stripe_processor.to_monospace('Charged 1$!')
            status_icon = "✅"
        elif status == 'ccn':
            status_text = self.stripe_processor.to_monospace('CCN Live!')
            status_icon = "🔥"
        elif status == 'declined':
            status_text = self.stripe_processor.to_monospace('Dead!')
            status_icon = "❌"
        else:
            status_text = self.stripe_processor.to_monospace('Error!')
            status_icon = "⚠️"
        
        return f"""TRIAL 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 <a href="{bot_link}">✿</a>
- - - - - - - - - - - - - - - - - - - - - - - -
<a href="{bot_link}">[⌯]</a> 𝗖𝗮𝗿𝗱 ⌁ <code>{card}</code>
<a href="{bot_link}">[⌯]</a> 𝗦𝘁𝗮𝘁𝘂𝘀 ⌁ {status_text} {status_icon}
<a href="{bot_link}">[⌯]</a> 𝗥𝗲𝘀𝘂𝗹𝘁 ⌁ {self.stripe_processor.to_monospace(response)}

<a href="{bot_link}">[⌯]</a> 𝗕𝗶𝗻 ⌁ {bin_display}
<a href="{bot_link}">[⌯]</a> 𝗕𝗮𝗻𝗸 ⌁ {bank_display}
<a href="{bot_link}">[⌯]</a> 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⌁ {country_display} {country_flag}

<a href="{bot_link}">[⌯]</a> 𝗚𝗮𝘁𝗲 ⌁ {self.stripe_processor.to_monospace('B3 Charge 1$')}
<a href="{bot_link}">[⌯]</a> 𝗨𝘀𝗲𝗱 𝗕𝘆 ⌁ <a href="{user_link}">{self.stripe_processor.to_monospace(username)}</a>
- - - - - - - - - - - - - - - - - - - - - - - -"""
    
    async def mbc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mass B3 check - reply to file with /mbc"""
        user = update.effective_user
        user_id = user.id
        
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐑𝐞𝐩𝐥𝐲 𝐓𝐨 𝐀 𝐅𝐢𝐥𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐖𝐢𝐭𝐡 /mbc\n\n"
                "📁 𝐇𝐨𝐰 𝐓𝐨 𝐔𝐬𝐞:\n"
                "1. Upload your combo file\n"
                "2. Reply to that file message with /mbc"
            )
            return
        
        replied_message = update.message.reply_to_message
        filename = None
        
        if user_id in self.user_files:
            filename = self.user_files[user_id]
            if not os.path.exists(filename):
                del self.user_files[user_id]
                filename = None
        
        if not filename and replied_message.document:
            try:
                file = await replied_message.document.get_file()
                filename = f"b3_combos_{user_id}_{datetime.now().timestamp()}.txt"
                await file.download_to_drive(filename)
            except Exception as e:
                logger.error(f"File download error: {str(e)}")
                await update.message.reply_text("❌ Failed to download file!")
                return
        
        if not filename:
            await update.message.reply_text("❌ No file found! Please upload a file first.")
            return
        
        if user_id in self.active_tasks:
            await update.message.reply_text("⚠️ Existing process found! Use /stop to cancel")
            return
        
        self.stop_flags[user_id] = False
        
        with open(filename, 'r') as f:
            combos = []
            for line in f:
                line = line.strip()
                if line:
                    card = self.extract_card_from_text(line)
                    if card:
                        combos.append(card)
        
        if not combos:
            await update.message.reply_text("❌ No valid cards found in the file!")
            return
        
        stats = {
            'total': len(combos),
            'approved': 0,
            'ccn': 0,
            'declined': 0,
            'errors': 0,
            'checked': 0,
            'start_time': datetime.now(),
            'last_response': 'Starting...'
        }
        
        keyboard = [
            [InlineKeyboardButton("✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 0", callback_data=f'b3stat_approved_{user_id}')],
            [InlineKeyboardButton("🔥 𝗖𝗖𝗡 0", callback_data=f'b3stat_ccn_{user_id}')],
            [InlineKeyboardButton("❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 0", callback_data=f'b3stat_declined_{user_id}')],
            [InlineKeyboardButton("💎 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 Starting...", callback_data=f'b3stat_response_{user_id}')],
            [InlineKeyboardButton(f"💳 𝗧𝗼𝘁𝗮𝗹 0/{len(combos)}", callback_data=f'b3stat_total_{user_id}')],
            [InlineKeyboardButton("⏹️ 𝗦𝘁𝗼𝗽", callback_data=f'b3stop_{user_id}')]
        ]
        
        status_message = await update.message.reply_text(
            f"🔄 <b>𝙱𝟹 𝙼𝚊𝚜𝚜 𝙲𝚑𝚎𝚌𝚔 𝚂𝚝𝚊𝚛𝚝𝚎𝚍</b>\n\n"
            f"<b>⌁ 𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀:</b> {len(combos)}\n"
            f"<b>⌁ 𝗚𝗮𝘁𝗲:</b> B3 Charge [1$]\n"
            f"<b>⌁ 𝗦𝘁𝗮𝘁𝘂𝘀:</b> Processing...",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        self.active_tasks[user_id] = asyncio.create_task(
            self.process_b3_mass_check(user_id, combos, update, status_message, stats)
        )
    
    async def process_b3_mass_check(self, user_id, combos, update, status_message, stats):
        user = update.effective_user
        approved_cards = []
        ccn_cards = []
        
        try:
            for combo in combos:
                if self.stop_flags.get(user_id, False):
                    break
                
                cc, mm, yy, cvv = combo.split('|')
                card = f"{cc}|{mm}|{yy}|{cvv}"
                
                try:
                    try:
                        result = await asyncio.wait_for(gate5.check_card(cc, mm, yy, cvv), timeout=15)
                    except asyncio.TimeoutError:
                        result = {'status': 'error', 'message': 'Timeout (15s)'}
                    stats['checked'] += 1
                    stats['last_response'] = result.get('message', 'N/A')[:20]
                    
                    if result['status'] == 'approved':
                        stats['approved'] += 1
                        approved_cards.append(card)
                        bin_info = await self.fetch_bin_info(cc[:6])
                        msg = self.format_b3_message(card, bin_info, result, user, 'approved')
                        await update.message.reply_text(msg, parse_mode='HTML')
                    elif result['status'] == 'ccn':
                        stats['ccn'] += 1
                        ccn_cards.append(card)
                        bin_info = await self.fetch_bin_info(cc[:6])
                        msg = self.format_b3_message(card, bin_info, result, user, 'ccn')
                        await update.message.reply_text(msg, parse_mode='HTML')
                    elif result['status'] == 'declined':
                        stats['declined'] += 1
                    else:
                        stats['errors'] += 1
                    
                    keyboard = [
                        [InlineKeyboardButton(f"✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 {stats['approved']}", callback_data=f'b3stat_approved_{user_id}')],
                        [InlineKeyboardButton(f"🔥 𝗖𝗖𝗡 {stats['ccn']}", callback_data=f'b3stat_ccn_{user_id}')],
                        [InlineKeyboardButton(f"❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 {stats['declined']}", callback_data=f'b3stat_declined_{user_id}')],
                        [InlineKeyboardButton(f"💎 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 {stats.get('last_response', 'N/A')[:20]}", callback_data=f'b3stat_response_{user_id}')],
                        [InlineKeyboardButton(f"💳 𝗧𝗼𝘁𝗮𝗹 {stats['checked']}/{stats['total']}", callback_data=f'b3stat_total_{user_id}')],
                        [InlineKeyboardButton("⏹️ 𝗦𝘁𝗼𝗽", callback_data=f'b3stop_{user_id}')]
                    ]
                    
                    try:
                        await status_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
                    except:
                        pass
                        
                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"B3 check error: {e}")
                
                if not self.stop_flags.get(user_id, False):
                    await asyncio.sleep(15)
            
            elapsed = (datetime.now() - stats['start_time']).total_seconds()
            
            final_msg = (
                f"✅ <b>𝙱𝟹 𝙼𝚊𝚜𝚜 𝙲𝚑𝚎𝚌𝚔 𝙲𝚘𝚖𝚙𝚕𝚎𝚝𝚎𝚍</b>\n\n"
                f"<b>⌁ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱:</b> {stats['approved']}\n"
                f"<b>⌁ 𝗖𝗖𝗡 𝗟𝗶𝘃𝗲:</b> {stats['ccn']}\n"
                f"<b>⌁ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱:</b> {stats['declined']}\n"
                f"<b>⌁ 𝗘𝗿𝗿𝗼𝗿𝘀:</b> {stats['errors']}\n"
                f"<b>⌁ 𝗧𝗼𝘁𝗮𝗹:</b> {stats['checked']}/{stats['total']}\n"
                f"<b>⌁ 𝗧𝗶𝗺𝗲:</b> {elapsed:.2f}s\n"
                f"<b>⌁ 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗕𝘆:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>"
            )
            
            try:
                await status_message.edit_text(final_msg, parse_mode='HTML')
            except:
                await update.message.reply_text(final_msg, parse_mode='HTML')
                
        except Exception as e:
            logger.error(f"B3 mass check error: {e}")
        finally:
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
    
    async def fetch_bin_info(self, bin_number):
        """Fetch BIN information"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://bins.antipublic.cc/bins/{bin_number}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            'brand': data.get('brand', 'N/A'),
                            'type': data.get('type', 'N/A'),
                            'level': data.get('level', 'N/A'),
                            'bank': data.get('bank', 'N/A'),
                            'country': data.get('country_name', 'N/A'),
                            'flag': data.get('country_flag', '')
                        }
        except:
            pass
        return {'brand': 'N/A', 'type': 'N/A', 'level': 'N/A', 'bank': 'N/A', 'country': 'N/A', 'flag': ''}
    
    async def mash_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mass check up to 20 cards with Shopify"""
        user = update.effective_user
        user_id = user.id
        
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        if user_id in self.gate4_active_tasks:
            await update.message.reply_text("⏳ You already have a Shopify check running! Use /stop first.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Usage: /mash cc|mm|yy|cvv (up to 20 cards, one per line)")
            return
        
        cards_text = ' '.join(context.args)
        card_pattern = r'(\d{13,19})[|/](\d{1,2})[|/](\d{2,4})[|/](\d{3,4})'
        cards = re.findall(card_pattern, cards_text)
        
        if not cards:
            await update.message.reply_text("❌ No valid cards found! Format: cc|mm|yy|cvv")
            return
        
        cards = cards[:20]
        
        user_sites = get_sites(user_id=user_id, bot_sites=False)
        use_user_sites = False
        
        if user_sites:
            keyboard = [
                [InlineKeyboardButton("🏠 Use My Sites", callback_data=f'g4_use_own_{user_id}')],
                [InlineKeyboardButton("🤖 Use Bot Sites", callback_data=f'g4_use_bot_{user_id}')]
            ]
            await update.message.reply_text(
                "🛒 Which sites do you want to use?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await asyncio.sleep(3)
            use_user_sites = self.gate4_user_site_choice.get(user_id, False)
        
        self.gate4_stats[user_id] = {
            'total': len(cards),
            'checked': 0,
            'charged': 0,
            'approved': 0,
            'declined': 0,
            'errors': 0,
            'start_time': datetime.now(),
            'last_response': 'Starting...'
        }
        self.gate4_stop_flags[user_id] = False
        
        keyboard = [
            [InlineKeyboardButton(f"𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥 0", callback_data=f'g4stat_charged_{user_id}')],
            [InlineKeyboardButton(f"𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅ 0", callback_data=f'g4stat_approved_{user_id}')],
            [InlineKeyboardButton(f"𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ 0", callback_data=f'g4stat_declined_{user_id}')],
            [InlineKeyboardButton(f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 Starting...", callback_data=f'g4stat_response_{user_id}')],
            [InlineKeyboardButton(f"𝗧𝗼𝘁𝗮𝗹 💳 0/{len(cards)}", callback_data=f'g4stat_total_{user_id}')],
            [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g4stop_{user_id}')]
        ]
        status_message = await update.message.reply_text(
            f"🛒 𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸\n𝗖𝗮𝗿𝗱𝘀: {len(cards)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        task = asyncio.create_task(self._run_mash_check(update, cards, user_id, status_message, use_user_sites))
        self.gate4_active_tasks[user_id] = task
    
    async def _run_mash_check(self, update, cards, user_id, status_message, use_user_sites):
        """Run mass Shopify check"""
        try:
            for i, (cc, mes, ano, cvv) in enumerate(cards):
                if self.gate4_stop_flags.get(user_id, False):
                    break
                
                result = await check_card_shopify(cc, mes, ano, cvv, user_id=user_id, use_user_sites=use_user_sites)
                self.gate4_stats[user_id]['checked'] += 1
                self.gate4_stats[user_id]['last_response'] = result.get('message', 'N/A')[:30]
                
                user = update.effective_user
                start_time = datetime.now()
                check_time = (datetime.now() - start_time).total_seconds()
                
                site = result.get('site', 'N/A')
                amount = result.get('amount', 'N/A')
                proxy = result.get('proxy', 'N/A')
                
                if result['status'] == 'charged':
                    self.gate4_stats[user_id]['charged'] += 1
                    bin_info = await self.fetch_bin_info(cc[:6])
                    card = f"{cc}|{mes}|{ano}|{cvv}"
                    message = g4_format_charged(card, bin_info, check_time, user, result.get('message', 'Charged'), site, amount, proxy)
                    await update.message.reply_text(message, parse_mode='HTML')
                elif result['status'] == 'approved':
                    self.gate4_stats[user_id]['approved'] += 1
                    bin_info = await self.fetch_bin_info(cc[:6])
                    card = f"{cc}|{mes}|{ano}|{cvv}"
                    message = g4_format_approved(card, bin_info, check_time, user, result.get('message', 'Approved'), site, amount, proxy)
                    await update.message.reply_text(message, parse_mode='HTML')
                elif result['status'] == 'declined':
                    self.gate4_stats[user_id]['declined'] += 1
                else:
                    self.gate4_stats[user_id]['errors'] += 1
                
                await self.update_gate4_status_buttons(user_id, status_message)
            
            if not self.gate4_stop_flags.get(user_id, False):
                stats = self.gate4_stats[user_id]
                elapsed = datetime.now() - stats['start_time']
                report = f"""━━━━━━━━━━━━━━━━━━━━━━
🛒 𝗦𝗛𝗢𝗣𝗜𝗙𝗬 𝗖𝗛𝗘𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘
━━━━━━━━━━━━━━━━━━━━━━
𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥: {stats['charged']}
𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅: {stats.get('approved', 0)}
𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌: {stats['declined']}
𝗘𝗿𝗿𝗼𝗿𝘀 ⚠️: {stats['errors']}
𝗧𝗼𝘁𝗮𝗹 💳: {stats['checked']}/{stats['total']}
𝗧𝗶𝗺𝗲 ⏱️: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
━━━━━━━━━━━━━━━━━━━━━━"""
                await update.message.reply_text(report)
        except Exception as e:
            logger.error(f"Gate4 mass check error: {str(e)}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
        finally:
            if user_id in self.gate4_active_tasks:
                del self.gate4_active_tasks[user_id]
            if user_id in self.gate4_stop_flags:
                del self.gate4_stop_flags[user_id]
            if user_id in self.gate4_stats:
                del self.gate4_stats[user_id]
    
    async def ashtxt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check cards from txt file with Shopify (max 1000)"""
        user = update.effective_user
        user_id = user.id
        
        if not await self.is_user_allowed(user_id):
            await update.message.reply_text("⛔ You need a subscription to use this command!")
            return
        
        if user_id in self.gate4_active_tasks:
            await update.message.reply_text("⏳ You already have a Shopify check running! Use /stop first.")
            return
        
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text("❌ Reply to a .txt file with /ashtxt")
            return
        
        document = update.message.reply_to_message.document
        if not document.file_name.endswith('.txt'):
            await update.message.reply_text("❌ Please upload a .txt file!")
            return
        
        file = await document.get_file()
        filename = f"/tmp/shopify_{user_id}.txt"
        await file.download_to_drive(filename)
        
        with open(filename, 'r') as f:
            content = f.read()
        
        card_pattern = r'(\d{13,19})[|/](\d{1,2})[|/](\d{2,4})[|/](\d{3,4})'
        cards = re.findall(card_pattern, content)
        
        if not cards:
            os.remove(filename)
            await update.message.reply_text("❌ No valid cards found in file!")
            return
        
        cards = cards[:self.gate4_max_cards]
        
        user_sites = get_sites(user_id=user_id, bot_sites=False)
        use_user_sites = False
        
        if user_sites:
            keyboard = [
                [InlineKeyboardButton("🏠 Use My Sites", callback_data=f'g4_use_own_{user_id}')],
                [InlineKeyboardButton("🤖 Use Bot Sites", callback_data=f'g4_use_bot_{user_id}')]
            ]
            await update.message.reply_text(
                "🛒 Which sites do you want to use?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await asyncio.sleep(3)
            use_user_sites = self.gate4_user_site_choice.get(user_id, False)
        
        self.gate4_stats[user_id] = {
            'total': len(cards),
            'checked': 0,
            'charged': 0,
            'approved': 0,
            'declined': 0,
            'errors': 0,
            'start_time': datetime.now(),
            'last_response': 'Starting...'
        }
        self.gate4_stop_flags[user_id] = False
        
        keyboard = [
            [InlineKeyboardButton(f"𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥 0", callback_data=f'g4stat_charged_{user_id}')],
            [InlineKeyboardButton(f"𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅ 0", callback_data=f'g4stat_approved_{user_id}')],
            [InlineKeyboardButton(f"𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ 0", callback_data=f'g4stat_declined_{user_id}')],
            [InlineKeyboardButton(f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 Starting...", callback_data=f'g4stat_response_{user_id}')],
            [InlineKeyboardButton(f"𝗧𝗼𝘁𝗮𝗹 💳 0/{len(cards)}", callback_data=f'g4stat_total_{user_id}')],
            [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g4stop_{user_id}')]
        ]
        status_message = await update.message.reply_text(
            f"🛒 𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸\n𝗖𝗮𝗿𝗱𝘀: {len(cards)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        task = asyncio.create_task(self._run_ashtxt_check(update, cards, user_id, status_message, use_user_sites, filename))
        self.gate4_active_tasks[user_id] = task
    
    async def _run_ashtxt_check(self, update, cards, user_id, status_message, use_user_sites, filename):
        """Run txt file Shopify check"""
        try:
            for i, (cc, mes, ano, cvv) in enumerate(cards):
                if self.gate4_stop_flags.get(user_id, False):
                    break
                
                result = await check_card_shopify(cc, mes, ano, cvv, user_id=user_id, use_user_sites=use_user_sites)
                self.gate4_stats[user_id]['checked'] += 1
                self.gate4_stats[user_id]['last_response'] = result.get('message', 'N/A')[:30]
                
                user = update.effective_user
                start_time = datetime.now()
                check_time = (datetime.now() - start_time).total_seconds()
                
                site = result.get('site', 'N/A')
                amount = result.get('amount', 'N/A')
                proxy = result.get('proxy', 'N/A')
                
                if result['status'] == 'charged':
                    self.gate4_stats[user_id]['charged'] += 1
                    bin_info = await self.fetch_bin_info(cc[:6])
                    card = f"{cc}|{mes}|{ano}|{cvv}"
                    message = g4_format_charged(card, bin_info, check_time, user, result.get('message', 'Charged'), site, amount, proxy)
                    await update.message.reply_text(message, parse_mode='HTML')
                elif result['status'] == 'approved':
                    self.gate4_stats[user_id]['approved'] += 1
                    bin_info = await self.fetch_bin_info(cc[:6])
                    card = f"{cc}|{mes}|{ano}|{cvv}"
                    message = g4_format_approved(card, bin_info, check_time, user, result.get('message', 'Approved'), site, amount, proxy)
                    await update.message.reply_text(message, parse_mode='HTML')
                elif result['status'] == 'declined':
                    self.gate4_stats[user_id]['declined'] += 1
                else:
                    self.gate4_stats[user_id]['errors'] += 1
                
                await self.update_gate4_status_buttons(user_id, status_message)
            
            if not self.gate4_stop_flags.get(user_id, False):
                stats = self.gate4_stats[user_id]
                elapsed = datetime.now() - stats['start_time']
                report = f"""━━━━━━━━━━━━━━━━━━━━━━
🛒 𝗦𝗛𝗢𝗣𝗜𝗙𝗬 𝗖𝗛𝗘𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘
━━━━━━━━━━━━━━━━━━━━━━
𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥: {stats['charged']}
𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅: {stats.get('approved', 0)}
𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌: {stats['declined']}
𝗘𝗿𝗿𝗼𝗿𝘀 ⚠️: {stats['errors']}
𝗧𝗼𝘁𝗮𝗹 💳: {stats['checked']}/{stats['total']}
𝗧𝗶𝗺𝗲 ⏱️: {elapsed.seconds // 60}m {elapsed.seconds % 60}s
━━━━━━━━━━━━━━━━━━━━━━"""
                await update.message.reply_text(report)
        except Exception as e:
            logger.error(f"Gate4 txt check error: {str(e)}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            if user_id in self.gate4_active_tasks:
                del self.gate4_active_tasks[user_id]
            if user_id in self.gate4_stop_flags:
                del self.gate4_stop_flags[user_id]
            if user_id in self.gate4_stats:
                del self.gate4_stats[user_id]
    
    async def update_gate4_status_buttons(self, user_id, status_message):
        """Update Gate 4 inline buttons with current stats"""
        try:
            stats = self.gate4_stats.get(user_id, {})
            keyboard = [
                [InlineKeyboardButton(f"𝗖𝗵𝗮𝗿𝗴𝗲𝗱 🔥 {stats.get('charged', 0)}", callback_data=f'g4stat_charged_{user_id}')],
                [InlineKeyboardButton(f"𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅ {stats.get('approved', 0)}", callback_data=f'g4stat_approved_{user_id}')],
                [InlineKeyboardButton(f"𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ❌ {stats.get('declined', 0)}", callback_data=f'g4stat_declined_{user_id}')],
                [InlineKeyboardButton(f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 💎 {stats.get('last_response', 'N/A')[:20]}", callback_data=f'g4stat_response_{user_id}')],
                [InlineKeyboardButton(f"𝗧𝗼𝘁𝗮𝗹 💳 {stats.get('checked', 0)}/{stats.get('total', 0)}", callback_data=f'g4stat_total_{user_id}')],
                [InlineKeyboardButton("𝗦𝘁𝗼𝗽 ⏹️", callback_data=f'g4stop_{user_id}')]
            ]
            await status_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Failed to update gate4 status buttons: {str(e)}")

    async def gen_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate credit cards from BIN"""
        if not await self.is_user_allowed(update.effective_user.id):
            await update.message.reply_text("⛔ You are not authorized!")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "❌ <b>Usage:</b> <code>/gen &lt;bin&gt; [quantity]</code>\n"
                "📌 <b>Example:</b> <code>/gen 527690 10</code>",
                parse_mode='HTML'
            )
            return
        
        bin_input = args[0].strip()
        quantity = 10
        
        if len(args) > 1:
            try:
                quantity = min(int(args[1]), 50)
            except ValueError:
                quantity = 10
        
        if len(bin_input) < 6:
            await update.message.reply_text("❌ BIN must be at least 6 digits!")
            return
        
        bin_6 = bin_input[:6]
        
        processing_msg = await update.message.reply_text("⏳ 𝙶𝚎𝚗𝚎𝚛𝚊𝚝𝚒𝚗𝚐...")
        
        try:
            bin_info = await self.fetch_bin_info(bin_6)
            
            def luhn_checksum(card_number):
                def digits_of(n):
                    return [int(d) for d in str(n)]
                digits = digits_of(card_number)
                odd_digits = digits[-1::-2]
                even_digits = digits[-2::-2]
                checksum = sum(odd_digits)
                for d in even_digits:
                    checksum += sum(digits_of(d * 2))
                return checksum % 10
            
            def generate_card(bin_prefix):
                import random
                card_length = 16
                remaining = card_length - len(bin_prefix) - 1
                card = bin_prefix + ''.join([str(random.randint(0, 9)) for _ in range(remaining)])
                checksum = luhn_checksum(int(card + '0'))
                check_digit = (10 - checksum) % 10
                return card + str(check_digit)
            
            cards = []
            for _ in range(quantity):
                cc = generate_card(bin_input if len(bin_input) <= 15 else bin_input[:15])
                month = str(random.randint(1, 12)).zfill(2)
                year = str(random.randint(2025, 2030))
                cvv = str(random.randint(100, 999))
                cards.append(f"{cc}|{month}|{year}|{cvv}")
            
            card_type = bin_info.get('type', 'N/A').upper()
            brand = bin_info.get('brand', 'N/A').upper()
            level = bin_info.get('level', 'N/A').upper()
            bank = bin_info.get('bank', 'N/A')
            country = bin_info.get('country', 'N/A')
            flag = bin_info.get('flag', '🏳️')
            
            cards_text = "\n".join([f"<code>{card}</code>" for card in cards])
            
            response = f"""━━━━━━━━━━━━━━━━━━━━━━
🎰 𝙲𝙲 𝙶𝙴𝙽𝙴𝚁𝙰𝚃𝙾𝚁
━━━━━━━━━━━━━━━━━━━━━━

<b>⌁ 𝗕𝗜𝗡:</b> <code>{bin_6}</code>
<b>⌁ 𝗔𝗺𝗼𝘂𝗻𝘁:</b> {len(cards)}

{cards_text}

━━━━━━━━━━━━━━━━━━━━━━
<b>⌁ 𝗜𝗻𝗳𝗼:</b> {card_type} - {level} - {brand}
<b>⌁ 𝗜𝘀𝘀𝘂𝗲𝗿:</b> {bank}
<b>⌁ 𝗖𝗼𝘂𝗻𝘁𝗿𝘆:</b> {country} {flag}
━━━━━━━━━━━━━━━━━━━━━━"""
            
            await processing_msg.edit_text(response, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Gen command error: {str(e)}")
            await processing_msg.edit_text(f"❌ Error: {str(e)}")

    async def dot_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle commands with dot prefix (e.g., .chk instead of /chk)"""
        text = update.message.text.strip()
        if not text.startswith('.'):
            return
        
        parts = text[1:].split(maxsplit=1)
        if not parts:
            return
        
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        context.args = args.split() if args else []
        
        command_map = {
            'start': self.start,
            'stop': self.stop_command,
            'stats': self.show_stats,
            'info': self.info_command,
            'help': self.show_help,
            'cmds': self.cmds_command,
            'chk': self.chk_command,
            'fchk': self.fchk_command,
            'sc': self.sc_command,
            'msc': self.msc_command,
            'rzp': self.rzp_command,
            'mrzp': self.mrzp_command,
            'ash': self.ash_command,
            'mash': self.mash_command,
            'ashtxt': self.ashtxt_command,
            'bc': self.bc_command,
            'mbc': self.mbc_command,
            'gen': self.gen_command,
            'clean': cleaner_tools.clean_command,
            'ccn': cleaner_tools.cards_command,
            'ulp': cleaner_tools.ulp_command,
            'txt': cleaner_tools.txt_command,
            'split': cleaner_tools.split_command,
            'bin': cleaner_tools.bin_filter_command,
            'sort': cleaner_tools.sort_command,
            'chkproxy': proxy_checker.chkproxy_command,
            'clp': proxy_checker.clp_command,
            'ptxt': proxy_checker.ptxt_command,
            'genkey': self.genkey_command,
            'redeem': self.redeem_command,
            'addadmin': self.addadmin_command,
            'rmadmin': self.removeadmin_command,
            'listadmins': self.listadmins_command,
            'listalloweduser': self.listalloweduser_command,
            'listsubscription': self.listsubscription_command,
            'addproxy': self.addproxy_command,
            'reloadproxies': self.reloadproxies_command,
            'fproxies': self.fproxies_command,
            'addsite': self.addsite_command,
            'rmsite': self.rmsite_command,
            'listsite': self.listsite_command,
        }
        
        handler = command_map.get(cmd)
        if handler:
            await handler(update, context)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(msg="Exception:", exc_info=context.error)
        await self.send_message(update, f"⚠️ System Error: {str(context.error)}")

def main():
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable is not set!")
        print("Please set your Telegram bot token in the Secrets tab.")
        return
    
    checker = AdvancedCardChecker()
    application = Application.builder().token(bot_token).post_init(checker.post_init).concurrent_updates(True).build()
    checker.application = application
    
    handlers = [
        CommandHandler('start', checker.start),
        CommandHandler('allow', checker.handle_admin_command),
        CommandHandler('deny', checker.handle_admin_command),
        CommandHandler('stop', checker.stop_command),
        CommandHandler('stats', checker.show_stats),
        CommandHandler('info', checker.info_command),
        CommandHandler('help', checker.show_help),
        CommandHandler('cmds', checker.cmds_command),
        CommandHandler('chk', checker.chk_command),
        CommandHandler('fchk', checker.fchk_command),
        CommandHandler('sc', checker.sc_command),
        CommandHandler('msc', checker.msc_command),
        CommandHandler('rzp', checker.rzp_command),
        CommandHandler('mrzp', checker.mrzp_command),
        CommandHandler('broadcast', checker.broadcast_command),
        CommandHandler('genkey', checker.genkey_command),
        CommandHandler('redeem', checker.redeem_command),
        CommandHandler('addadmin', checker.addadmin_command),
        CommandHandler('rmadmin', checker.removeadmin_command),
        CommandHandler('listadmins', checker.listadmins_command),
        CommandHandler('listalloweduser', checker.listalloweduser_command),
        CommandHandler('listsubscription', checker.listsubscription_command),
        CommandHandler('delkey', checker.delkey_command),
        CommandHandler('addproxy', checker.addproxy_command),
        CommandHandler('reloadproxies', checker.reloadproxies_command),
        CommandHandler('fproxies', checker.fproxies_command),
        CommandHandler('addsite', checker.addsite_command),
        CommandHandler('rmsite', checker.rmsite_command),
        CommandHandler('listsite', checker.listsite_command),
        CommandHandler('chksite', checker.chksite_command),
        CommandHandler('chkaddedsite', checker.chkaddedsite_command),
        CommandHandler('asm', checker.asm_command),
        CommandHandler('ash', checker.ash_command),
        CommandHandler('bc', checker.bc_command),
        CommandHandler('mbc', checker.mbc_command),
        CommandHandler('mash', checker.mash_command),
        CommandHandler('ashtxt', checker.ashtxt_command),
        CommandHandler('clean', cleaner_tools.clean_command),
        CommandHandler('ccn', cleaner_tools.cards_command),
        CommandHandler('ulp', cleaner_tools.ulp_command),
        CommandHandler('txt', cleaner_tools.txt_command),
        CommandHandler('split', cleaner_tools.split_command),
        CommandHandler('bin', cleaner_tools.bin_filter_command),
        CommandHandler('sort', cleaner_tools.sort_command),
        CommandHandler('gen', checker.gen_command),
        CommandHandler('chkproxy', proxy_checker.chkproxy_command),
        CommandHandler('clp', proxy_checker.clp_command),
        CommandHandler('ptxt', proxy_checker.ptxt_command),
        MessageHandler(filters.Document.TXT, checker.handle_file),
        MessageHandler(filters.TEXT & filters.Regex(r'^\.'), checker.dot_command_handler),
        CallbackQueryHandler(checker.button_handler)
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    application.add_error_handler(checker.error_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
