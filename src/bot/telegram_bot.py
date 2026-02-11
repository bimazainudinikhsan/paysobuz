import logging
import asyncio
import io
import qrcode
from PIL import Image
import json
import os
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from src.core.auth import AuthManager
from src.core.api import APIManager
from src.core.transactions import TransactionManager
from src.core.database import PaymentDatabase
from config.settings import Config

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class SocialBuzzBot:
    def __init__(self):
        self.auth = AuthManager()
        self.api = APIManager(self.auth) # Pass AuthManager directly
        self.tm = TransactionManager(self.auth)
        self.db = PaymentDatabase()
        self.monitoring_task = None
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Delete user's /start message to keep chat clean
        try:
            await update.message.delete()
        except Exception:
            pass

        # Check Channel Membership
        if not await self.check_channel_membership(update, context):
            return

        # Start background monitoring if not running
        if self.monitoring_task is None or self.monitoring_task.done():
             self.monitoring_task = asyncio.create_task(self.monitor_pending_payments(context.application))
             
        # Check authorization removed from here because show_dashboard handles it
        # if not self._is_authorized(update):
        #    await update.message.reply_text("Unauthorized access.")
        #    return

        await self.show_dashboard(update, context)

    async def _check_single_payment(self, app, payment):
        try:
            print(f"[DEBUG_FLOW] 🔍 Monitoring payment {payment['id']} ({payment.get('method')})...")
            method = payment.get('method')
            status_info = None
            
            # Extract common details
            details = payment.get('details', {})
            token = details.get('token')
            
            # For status checking, we prefer the SociaBuzz payment URL (payment.get('url'))
            # because it reliably displays status ("Waiting for payment", "Success") 
            # regardless of the payment method (DANA, OVO, Bank, etc.).
            # External redirect URLs (like m.dana.id) often cannot be scraped.
            url = payment.get('url')
            
            # Fallback to redirect_url only if main URL is missing
            if not url:
                 url = details.get('redirect_url')
            
            # Reconstruct URL if missing (fallback logic)
            if not url and token and len(token) > 30 and '-' in token:
                 url = f"https://sociabuzz.com/payment/x/{token}"
            
            # Check status for ALL methods (gopay, ovo, qris, banks, etc.)
            # passing both token and url ensures best chance of checking
            status_info = self.api.check_payment_status(token, method, url)
            
            if status_info:
                status_code = status_info.get('status_code')
                status_msg = status_info.get('status')
                
                if str(status_code) == "200" or status_msg == "settlement":
                    # SUCCESS!
                    print(f"✅ Payment {payment['id']} SUCCESS!")
                    
                    # Update DB (merged automatically now)
                    self.db.update_payment_status(payment['id'], "success", status_info)
                    
                    user_id = payment['user_id']
                    
                    # Extract details from current payment object (safe because we haven't re-fetched)
                    details = payment.get('details', {})
                    message_id = details.get('message_id')
                    loading_message_id = details.get('loading_message_id')
                    
                    # Check if there is a final_amount (including fees)
                    final_amount = details.get('final_amount')
                    if final_amount:
                        amount = final_amount
                    else:
                        amount = payment['amount']
                    
                    # Format nominal rupiah
                    try:
                         amount_val = float(amount)
                         formatted_amount = f"Rp{amount_val:,.0f}".replace(",", ".")
                    except:
                         formatted_amount = f"Rp{amount}"

                    # Get Transaction ID (Use order_id if possible, otherwise internal ID)
                    transaction_id = payment.get('id', 'Unknown')
                    if 'pay_' in transaction_id and '_' in transaction_id:
                         # Try to make it look cleaner if it's our internal timestamp ID
                         transaction_id = transaction_id.split('_')[-1] # User ID part isn't unique enough, stick to full or order_id
                    
                    # Use Donor name
                    donor_name = payment.get('donor_name', 'Supporter')
                    
                    success_text = (
                        f"✅ *Pembayaran Berhasil*\n\n"
                        f"🆔 *ID:* `{transaction_id}`\n"
                        f" *Metode:* {method.upper()}\n"
                        f"💰 *Nominal:* `{formatted_amount}`\n"
                        f"✅ *Status:* Lunas\n\n"
                        f"_Terima kasih! Pembayaran Anda telah kami terima._"
                    )
                    
                    # Show dashboard button for everyone
                    success_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Kembali ke Dashboard", callback_data='back_to_menu')
                    ]])

                    if message_id:
                        try:
                            await app.bot.delete_message(chat_id=user_id, message_id=message_id)
                        except Exception as e:
                            print(f"Failed to delete QRIS message: {e}")
                    
                    # Always send a new success message
                    await app.bot.send_message(
                        chat_id=user_id, 
                        text=success_text, 
                        reply_markup=success_markup, 
                        parse_mode='Markdown'
                    )
                    
                    # Delete "Creating payment link..." message if exists
                    if loading_message_id:
                        try:
                            await app.bot.delete_message(chat_id=user_id, message_id=loading_message_id)
                        except Exception as e:
                            print(f"Failed to delete loading message: {e}")

                elif status_msg == "expire" or status_msg == "cancel":
                     self.db.update_payment_status(payment['id'], "cancelled", status_info)
                     
                     # Delete QRIS message if expired too
                     details = payment.get('details', {})
                     message_id = details.get('message_id')
                     if message_id:
                         try:
                             await app.bot.delete_message(chat_id=payment['user_id'], message_id=message_id)
                         except:
                             pass
        except Exception as e:
            print(f"Error checking payment {payment['id']}: {e}")

    async def monitor_pending_payments(self, app):
        """Background task to check status of pending payments."""
        print("🚀 Background Payment Monitoring Started...")
        
        # Limit concurrency to avoid overloading the system/API
        # Since we use run_in_executor with default thread pool, 
        # we shouldn't queue too many tasks at once.
        semaphore = asyncio.Semaphore(5) 

        async def protected_check(payment):
            async with semaphore:
                await self._check_single_payment(app, payment)

        while True:
            try:
                # Reload pending payments every loop to get fresh data
                pending_payments = self.db.get_pending_payments()
                
                if pending_payments:
                    print(f"[DEBUG_MONITOR] Checking {len(pending_payments)} pending payments...")
                    
                    # Create tasks with semaphore protection
                    tasks = [protected_check(payment) for payment in pending_payments]
                    
                    # Run all (but limited by semaphore)
                    await asyncio.gather(*tasks)
                
                # Wait longer to reduce load (10 seconds is a good balance)
                await asyncio.sleep(10) 
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)

    async def show_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Check Channel Membership (for callbacks)
        if not await self.check_channel_membership(update, context):
            return

        if not self._is_authorized(update):
            # For regular users, show user info and history
            user = update.effective_user
            user_id = user.id
            full_name = user.full_name
            username = f"@{user.username}" if user.username else "-"
            
            # Get stats
            total_spent = self.db.get_user_success_total(user_id)
            formatted_total = f"Rp{total_spent:,.0f}".replace(",", ".")
            
            default_target = self.db.get_global_setting("default_target")
            target_display = default_target if default_target else "<username>"
            
            help_text = (
                f"👋 *Halo, {full_name}!*\n\n"
                f"👤 *Informasi Pengguna*\n"
                f"🆔 ID: `{user_id}`\n"
                f"👤 Username: {username}\n\n"
                f"💰 *Total Transaksi Berhasil:* `{formatted_total}`\n\n"
                f"💡 *Buat Pembayaran Baru:*\n"
                f"Tekan tombol di bawah untuk memulai."
            )
            
            keyboard = [
                [InlineKeyboardButton("💰 Buat Pembayaran", callback_data='create_payment_user')],
                [InlineKeyboardButton("📝 Riwayat Transaksi", callback_data='user_transactions')],
                [InlineKeyboardButton("⚙️ Pengaturan", callback_data='user_settings')],
                [InlineKeyboardButton("ℹ️ Informasi Bot", callback_data='bot_info')],
                [InlineKeyboardButton("💬 Hubungi Admin", url='https://t.me/nbxids')],
                [InlineKeyboardButton("🔄 Segarkan", callback_data='refresh')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if update.callback_query:
                await update.callback_query.answer()
                try:
                    await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        pass
                    else:
                        raise
            else:
                await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
            return

        keyboard = [
            [
                InlineKeyboardButton("📊 Status System", callback_data='status'),
                InlineKeyboardButton("📝 Log Transaksi", callback_data='transactions'),
            ],
            [
                InlineKeyboardButton("💸 Tarik Dana", callback_data='withdrawals'),
                InlineKeyboardButton("💰 Buat Link Bayar", callback_data='create_payment'),
            ],
            [
                InlineKeyboardButton("📢 Update Info", callback_data='admin_update_info'),
                InlineKeyboardButton("🔄 Refresh", callback_data='refresh'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🤖 *NBX ID Dashboard*\n\n"
            "Selamat datang di pusat kontrol Anda. Pilih tindakan di bawah ini:"
        )
        
        if update.callback_query:
            await update.callback_query.answer()
            try:
                await update.callback_query.edit_message_text(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    pass
                else:
                    raise
        else:
            await update.message.reply_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def show_bot_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Check if there is custom info from DB
        custom_info = self.db.get_bot_info()
        
        if custom_info:
            info_text = custom_info
        else:
            # Default Info
            info_text = (
                "🤖 *Informasi Bot*\n"
                "Versi: 1.0\n\n"
                "✨ *Kelebihan Bot:*\n"
                "✅ *Cepat & Otomatis:* Verifikasi pembayaran instan 24/7.\n"
                "✅ *Aman:* Menggunakan gateway pembayaran resmi.\n"
                "✅ *Mudah:* Mendukung berbagai metode pembayaran (QRIS, E-Wallet, Bank).\n"
                "✅ *Real-time:* Notifikasi status pembayaran langsung ke chat Anda.\n\n"
                "💳 *Limit Pembayaran:*\n"
                "• *E-Wallet (GoPay):* Min Rp1.000 - Max Rp10.000.000\n"
                "• *QRIS:* Min Rp1.000 - Max Rp5.000.000\n"
                "• *Virtual Account Bank:* Min Rp10.000 - Max Rp50.000.000\n\n"
                "🛠 *Pengembangan Custom:*\n"
                "Jika Anda ingin membuat program serupa untuk Website, Aplikasi, atau integrasi lainnya, silakan hubungi Admin kami.\n\n"
                "📞 *Kontak Admin:* @nbxids"
            )
        
        keyboard = [
            [InlineKeyboardButton("💬 Hubungi Admin", url='https://t.me/nbxids')],
            [InlineKeyboardButton("🔙 Kembali ke Dashboard", callback_data='back_to_menu')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.answer()
            try:
                await update.callback_query.edit_message_text(
                    text=info_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    pass
                else:
                    raise
        else:
            await update.message.reply_text(
                text=info_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def show_user_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id
        
        # Get current setting (default False as per user request)
        use_logo = self.db.get_user_setting(user_id, 'use_qris_logo', False)
        
        status_text = "✅ ON" if use_logo else "❌ OFF"
        toggle_text = f"Logo QRIS: {status_text}"
        
        text = (
            "⚙️ *Pengaturan Pengguna*\n\n"
            "Atur preferensi bot Anda di sini.\n\n"
            "*Tampilan QRIS:*\n"
            "Menampilkan logo di tengah QRIS untuk tampilan lebih profesional."
        )
        
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data='toggle_qris_logo')],
            [InlineKeyboardButton("🔙 Kembali ke Dashboard", callback_data='back_to_menu')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.answer()
            try:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    pass
                else:
                    raise
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        # await query.answer() # Moved inside specific handlers or generic answer

        if query.data == 'check_subscription':
            await query.answer()
            if await self.check_channel_membership(update, context):
                await query.edit_message_text("✅ Terima kasih sudah bergabung! Memuat menu...")
                # Add small delay or just show dashboard
                await self.show_dashboard(update, context)
            else:
                # check_channel_membership handles the "not member" UI
                pass
            return
            
        await query.answer()

        if query.data == 'status':
            await self.check_status(update, context)
        elif query.data == 'transactions':
            await self.view_transactions(update, context)
        elif query.data.startswith('view_transactions_page_'):
            await self.view_transactions(update, context)
        elif query.data == 'user_transactions':
            await self.view_user_transactions(update, context)
        elif query.data == 'user_settings':
            await self.show_user_settings(update, context)
        elif query.data == 'toggle_qris_logo':
            user_id = update.effective_user.id
            # Toggle logic
            current_setting = self.db.get_user_setting(user_id, 'use_qris_logo', False)
            new_setting = not current_setting
            self.db.set_user_setting(user_id, 'use_qris_logo', new_setting)
            # Refresh settings view
            await self.show_user_settings(update, context)
        elif query.data.startswith('user_transactions_page_'):
            await self.view_user_transactions(update, context)
        elif query.data == 'bot_info':
            await self.show_bot_info(update, context)
        elif query.data == 'withdrawals':
            await self.view_withdrawals(update, context)
        elif query.data.startswith('withdraw_select_'):
            method_code = query.data.split('_')[2]
            method_name = method_code.upper()
            await self._handle_withdrawal_selection(update, context, method_name, method_code)
        elif query.data.startswith('withdraw_proceed_'):
            # Get method code from callback data
            method_code = query.data.split('_')[2]
            
            # Get balance from transactions.json
            balance_val = 0
            try:
                if os.path.exists("transactions.json"):
                    with open("transactions.json", "r", encoding='utf-8') as f:
                        data = json.load(f)
                        if 'balance_info' in data and data['balance_info'].get('success'):
                            balance_val = data['balance_info'].get('balance', 0)
            except:
                pass
                
            formatted_balance = f"Rp{balance_val:,}".replace(",", ".")
            
            await query.edit_message_text(
                text=f"💰 *Pencairan Dana ke {method_code.upper()}*\n\n"
                     f"Saldo Anda: {formatted_balance}\n\n"
                     f"Silakan ketik jumlah yang ingin dicairkan (contoh: 50000):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ganti Metode", callback_data='withdrawals')]]),
                parse_mode='Markdown'
            )
            
            # Set state to wait for amount
            context.user_data['withdrawal_state'] = {
                'method_code': method_code,
                'method_name': method_code.upper(),
                'balance': balance_val
            }
            
        elif query.data.startswith('withdraw_confirm_'):
            parts = query.data.split('_')
            if len(parts) >= 4:
                method_code = parts[2]
                amount = int(parts[3])
                
                await query.edit_message_text(f"⏳ Memproses pencairan Rp{amount:,} via {method_code.upper()}...".replace(",", "."))
                
                # Execute Withdrawal
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, 
                    lambda: self.api.withdraw_funds(method_code, amount)
                )
                
                if result.get('status') == 'success':
                    await query.edit_message_text(
                        f"✅ *Pencairan Berhasil!*\n\n"
                        f"Permintaan pencairan Rp{amount:,} ke {method_code.upper()} telah dikirim.\n"
                        f"Pesan: {result.get('message')}".replace(",", "."),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali ke Menu", callback_data='withdrawals')]]),
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text(
                        f"❌ *Pencairan Gagal*\n\n"
                        f"Pesan: {result.get('message')}\n"
                        f"Raw: {result.get('raw', '')}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali ke Menu", callback_data='withdrawals')]]),
                        parse_mode='Markdown'
                    )
        elif query.data == 'set_default_target':
            context.user_data['setting_state'] = 'waiting_for_target'
            await query.edit_message_text(
                "Silakan ketik username target yang ingin dijadikan default.\n\n"
                "Contoh: `windahbasudara`",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data='back_to_menu')]])
            )
        elif query.data == 'create_payment':
            await query.edit_message_text(text="Untuk membuat pembayaran, gunakan perintah:\n/pay <username> <jumlah> <pesan>")
        elif query.data.startswith('dummy_'):
            await query.answer("Kategori")
        elif query.data == 'refresh':
            await self.show_dashboard(update, context)
        elif query.data == 'back_to_menu':
             await self.show_dashboard(update, context)
        elif query.data.startswith('pay_'):
            # Extract method (e.g. pay_gopay, pay_sahabat_sampoerna)
            method = query.data[4:] # Remove 'pay_' prefix
            
            print(f"[DEBUG_FLOW] 👆 User selected payment method: {method}")

            # Restricted methods (Under Development)
            # User request: OVO, Dana, Ewalet Lainnya Kecuali Gopay Dan Qris
            restricted_methods = ['ovo', 'dana', 'linkaja', 'shopeepay']
            # Note: Banks are not explicitly in the "Ewalet Lainnya" list, but usually "Ewalet Lainnya" implies all other E-Wallets.
            # If "Ewalet Lainnya" meant "Methods Other", then we should restrict banks too.
            # However, usually banks are separated.
            # Given the phrasing "OVO, Dana, Ewalet Lainnya", I will restrict all known E-Wallets except GoPay.
            
            if method in restricted_methods:
                await query.answer("⚠️ Payment Ini masih Dalam Pengembangan", show_alert=True)
                return

            await self.process_payment_selection(update, context, method)
        elif query.data.startswith('chk_'):
            # format: chk_{method}_{token_or_url}
            parts = query.data.split('_', 2)
            # chk_gopay_token
            
            if len(parts) >= 3:
                method = parts[1]
                token = parts[2]
                await self.check_payment_status(update, context, token, method)
            else:
                await query.edit_message_text("❌ Data tombol tidak valid.")
                
        elif query.data.startswith('check_status_'):
            # Legacy/Fallback support
            parts = query.data.split('_', 3)
            if len(parts) >= 3:
                method = parts[2]
                token = parts[3] if len(parts) > 3 else ""
                await self.check_payment_status(update, context, token, method)
            else:
                token = query.data.split('_', 2)[2]
                await self.check_payment_status(update, context, token, "gopay")
                
        elif query.data == 'create_payment_user':
            context.user_data['payment_state'] = 'waiting_for_amount'
            # Save the prompt message ID to delete it later
            context.user_data['payment_prompt_message_id'] = query.message.message_id
            await query.edit_message_text(
                "💰 *Buat Pembayaran Baru*\n\n"
                "Silakan ketik nominal yang ingin dibayarkan.\n"
                "Contoh: `50000`\n\n"
                "_(Pastikan angka saja, tanpa titik/koma)_",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data='cancel_payment_creation')]]),
                parse_mode='Markdown'
            )
        elif query.data == 'cancel_payment_creation':
             if 'payment_state' in context.user_data:
                 del context.user_data['payment_state']
             await self.show_dashboard(update, context)
        elif query.data == 'cancel_payment':
            await self.cancel_payment(update, context)
        elif query.data == 'change_method':
            await self.change_payment_method(update, context)
        elif query.data == 'admin_update_info':
            if not self._is_authorized(update):
                return
            
            # Get current info
            current_info = self.db.get_bot_info()
            if not current_info:
                current_info = "_Belum ada informasi yang diset._"

            context.user_data['setting_state'] = 'waiting_for_info_text'
            await query.edit_message_text(
                f"📝 *Update Informasi Bot*\n\n"
                f"ℹ️ *Pesan Saat Ini:*\n"
                f"```\n{current_info}\n```\n\n"
                f"👇 *Instruksi:*\n"
                f"Silakan kirim teks/pesan baru untuk informasi bot.\n"
                f"Anda bisa menyalin pesan di atas dan mengeditnya.\n"
                f"Pesan ini akan ditampilkan di menu 'Informasi Bot' dan dibroadcast ke Channel.\n\n"
                f"Gunakan format Markdown (Bold, Italic, dll) untuk tampilan menarik.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data='back_to_menu')]])
            )
        elif query.data == 'confirm_broadcast_info':
             if not self._is_authorized(update):
                return
             await self._execute_broadcast_info(update, context)
        elif query.data == 'cancel_broadcast':
             if 'pending_info_text' in context.user_data:
                 del context.user_data['pending_info_text']
             await self.show_dashboard(update, context)

    async def _execute_broadcast_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_data = context.user_data
        
        info_text = user_data.get('pending_info_text')
        if not info_text:
            await query.edit_message_text("❌ Terjadi kesalahan: Teks informasi hilang.")
            return
            
        # 1. Save to Database
        self.db.set_bot_info(info_text)
        
        # 2. Broadcast to Channel
        channel_username = Config.REQUIRED_CHANNEL_USERNAME
        broadcast_status = "Gagal mengirim ke channel."
        
        if channel_username:
            try:
                # Create button to open bot
                bot_username = context.bot.username
                keyboard = [[InlineKeyboardButton("🤖 Buka Bot", url=f"https://t.me/{bot_username}")]]
                
                await context.bot.send_message(
                    chat_id=channel_username,
                    text=info_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                broadcast_status = f"Berhasil dikirim ke {channel_username}."
            except Exception as e:
                broadcast_status = f"Gagal broadcast ke channel: {e}"
                logging.error(f"Broadcast error: {e}")
        else:
             broadcast_status = "Channel belum disetting di .env (REQUIRED_CHANNEL_USERNAME)."

        # 3. Cleanup and Notify Admin
        if 'pending_info_text' in user_data:
            del user_data['pending_info_text']
            
        await query.edit_message_text(
            f"✅ *Update Berhasil!*\n\n"
            f"Informasi bot telah diperbarui.\n"
            f"Status Broadcast: {broadcast_status}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali ke Dashboard", callback_data='back_to_menu')]])
        )

    async def cancel_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if 'active_payment' in context.user_data:
            # Update Database
            # We need to find the pending payment for this user
            user_id = update.effective_user.id
            pending = self.db.get_pending_payments()
            for p in pending:
                if p['user_id'] == user_id:
                     self.db.update_payment_status(p['id'], "cancelled_by_user")

            del context.user_data['active_payment']
            
            text = "❌ Pembayaran dibatalkan. Anda sekarang dapat membuat pembayaran baru."
            
            # Show dashboard button for everyone
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali ke Dashboard", callback_data='back_to_menu')]])
            
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=markup
                )
            else:
                await query.edit_message_text(
                    text=text,
                    reply_markup=markup
                )
        else:
            text = "Tidak ada pembayaran aktif untuk dibatalkan."
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
            else:
                await query.edit_message_text(text)

    async def change_payment_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        # Go back to method selection
        # Ensure we still have the payment URL
        active = context.user_data.get('active_payment')
        if not active or not active.get('url'):
            msg = "❌ Sesi kedaluwarsa atau tidak ada pembayaran aktif."
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
            else:
                await query.edit_message_text(msg)
            return

        keyboard = [
            # E-Wallet & QRIS Section
            [InlineKeyboardButton("💳 E-WALLET & QRIS", callback_data='dummy_header_ewallet')],
            [
                InlineKeyboardButton("GoPay", callback_data='pay_gopay')
            ],
            [
                InlineKeyboardButton("QRIS", callback_data='pay_qris')
            ],
            # Bank Section
            [InlineKeyboardButton("🏦 TRANSFER BANK", callback_data='dummy_header_bank')],
            [
                InlineKeyboardButton("Mandiri", callback_data='pay_mandiri'),
                InlineKeyboardButton("BRI", callback_data='pay_bri')
            ],
            [
                InlineKeyboardButton("BNI", callback_data='pay_bni'),
                InlineKeyboardButton("BSI", callback_data='pay_bsi'),
                InlineKeyboardButton("CIMB", callback_data='pay_cimb')
            ],
            [
                InlineKeyboardButton("Permata", callback_data='pay_permata'),
                InlineKeyboardButton("BJB", callback_data='pay_bjb'),
                InlineKeyboardButton("BNC", callback_data='pay_bnc')
            ],
            [
                InlineKeyboardButton("BCA", callback_data='pay_bca'),
                InlineKeyboardButton("Maybank", callback_data='pay_maybank'),
                InlineKeyboardButton("Sinarmas", callback_data='pay_sinarmas')
            ],
            [
                InlineKeyboardButton("❌ Batalkan Pembayaran", callback_data='cancel_payment')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        amount = active.get('amount', 0)
        fmt_amount = f"Rp{amount:,.0f}".replace(",", ".")
        date_str = active.get('date_str', datetime.now().strftime("%d %b %Y - %H:%M"))

        text = (
            f"🧾 *Detail Pembayaran*\n\n"
            f"🕒 *Waktu:* {date_str}\n"
            f"💰 *Nominal:* {fmt_amount}\n\n"
            f"✅ Link Pembayaran Aktif!\nPilih metode pembayaran untuk melanjutkan:"
        )
        
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def check_payment_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE, token: str, method: str = "gopay"):
        query = update.callback_query
        # await query.answer("Checking status...") # Done in button_handler but good to have feedback if slow
        
        # Get URL from active payment for ALL methods (fallback for scraping)
        url = None
        active = context.user_data.get('active_payment')
        if active:
            url = active.get('url')
        
        # If URL is missing but token looks like a UUID (SociaBuzz Order ID), reconstruct it
        if not url and token and len(token) > 30 and '-' in token:
             url = f"https://sociabuzz.com/payment/x/{token}"
        
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: self.api.check_payment_status(token, method=method, payment_url=url)
        )
        
        if result:
            status = result.get('status', 'unknown')
            code = result.get('status_code', '-')
            msg = result.get('message', '')
            
            icon = "⏳"
            if status == "settlement" or status == "capture" or "Success" in msg:
                icon = "✅"
                # Clear active payment on success
                if 'active_payment' in context.user_data:
                    del context.user_data['active_payment']
            elif status == "pending":
                icon = "⏳"
            elif status == "expire" or status == "cancel":
                icon = "❌"
                # Clear active payment on failure/expiry
                if 'active_payment' in context.user_data:
                    del context.user_data['active_payment']
                
            # Map status to friendly text
            status_map = {
                "settlement": "Berhasil Pembayaran",
                "capture": "Berhasil Pembayaran",
                "pending": "Menunggu Pembayaran",
                "expire": "Kedaluwarsa",
                "cancel": "Dibatalkan",
                "deny": "Ditolak"
            }
            status_display = status_map.get(status, status)

            # Format Amount
            amount_display = ""
            if active and 'amount' in active:
                try:
                    amt_val = int(active['amount'])
                    amount_display = f"Rp{amt_val:,}".replace(",", ".")
                except:
                    pass

            # Special handling for Bank Transfers with saved VA details
            va_number = active.get('va_number') if active else None
            
            # If BCA and VA not in active, try to fetch it
            if status == "pending" and method == "bca" and not va_number and token and not token.startswith('pay_'):
                 va_number = await loop.run_in_executor(None, lambda: self.api._get_bca_va_from_snap(token))
                 # Save it for next time
                 if va_number and active:
                     active['va_number'] = va_number
                     active['bank_name'] = 'BCA'
                     # Calculate expiry if missing
                     if 'expiry_str' not in active:
                         expiry_dt = datetime.now() + timedelta(hours=24)
                         active['expiry_str'] = expiry_dt.strftime("%d %b %Y - %H:%M UTC+7")

            # If we have VA number and status is pending, show the full details
            if status == "pending" and va_number:
                bank_name = active.get('bank_name', method.upper())
                expiry_str = active.get('expiry_str', active.get('expiry', '-'))
                
                text = (
                    f"⏳ *Menunggu Pembayaran ({bank_name})*\n\n"
                    f"Silakan transfer ke Nomor Virtual Account berikut:\n\n"
                    f"🏦 *Bank:* {bank_name}\n"
                    f"🔢 *Nomor VA:* `{va_number}`\n"
                    f"💰 *Total:* `{amount_display}`\n"
                    f"⏰ *Batas Waktu:* {expiry_str}\n\n"
                    f"_dapat dibayar dari bank mana pun_"
                )
            else:
                # Use Berhasil Pembayaran etc.
                text = f"{icon} *{status_display} ({method.upper()})*\n\n"
                
                if amount_display:
                    text += f"💰 *Nominal*: {amount_display}\n"
                
                text += f"📊 *Status*: {status_display}\n"
                
                # Hide code 201 as requested
                if str(code) != '201':
                     text += f"🔧 *Kode*: `{code}`\n"
                
                text += f"� *Pesan*: {msg}"
                
                # Add countdown info if available
                if active and 'expiry' in active:
                    text += f"\n\n⏰ *Batas Waktu*: `{active['expiry']}`"

            keyboard = []
            if status == "pending":
                # Keep checking
                keyboard.append([InlineKeyboardButton("🔄 Cek Lagi", callback_data=f'chk_{method}_{token}')])
                
                # Add GoJek button for Gopay method (Persist the button)
                if method == "gopay" and token and not token.startswith('pay_'):
                    # Reconstruct Midtrans Snap URL using the token
                    snap_url = f"https://app.midtrans.com/snap/v4/redirection/{token}"
                    keyboard.append([InlineKeyboardButton("📱 Buka Aplikasi GoJek", url=snap_url)])
                
                # Add BCA Snap Link button for BCA method (Fallback if VA fetch failed)
                elif method == "bca" and token and not token.startswith('pay_') and "Nomor VA" not in text:
                    # Reconstruct Midtrans Snap URL using the token
                    snap_url = f"https://app.midtrans.com/snap/v4/redirection/{token}"
                    keyboard.append([InlineKeyboardButton("🔗 Buka Pembayaran (Snap)", url=snap_url)])
                
                # Allow changing method or cancelling
                keyboard.append([
                    InlineKeyboardButton("💳 Ganti Metode", callback_data='change_method'),
                    InlineKeyboardButton("❌ Batal", callback_data='cancel_payment')
                ])
            else:
                # Show dashboard button for everyone
                keyboard.append([InlineKeyboardButton("🔙 Kembali ke Dashboard", callback_data='back_to_menu')])
            
            markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            if query.message.photo:
                # If pending and method is QRIS, try to update caption to keep QR visible
                if status == "pending" and method == "qris":
                    try:
                        await query.edit_message_caption(
                            caption=text,
                            reply_markup=markup,
                            parse_mode='Markdown'
                        )
                    except BadRequest as e:
                        if "Message is not modified" in str(e):
                            pass  # Ignore if content is same
                        else:
                            # Fallback if other edit error
                            await query.message.delete()
                            await context.bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=text,
                                reply_markup=markup,
                                parse_mode='Markdown'
                            )
                    except Exception:
                        # Fallback if edit fails
                        await query.message.delete()
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=text,
                            reply_markup=markup,
                            parse_mode='Markdown'
                        )
                else:
                    # Success/Fail or not QRIS -> Switch to text
                    await query.message.delete()
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=text,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )
            else:
                try:
                    await query.edit_message_text(
                        text=text,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        pass
                    else:
                        raise e
        else:
            msg = "❌ Gagal mengambil status pembayaran."
            if query.message.photo:
                 await query.message.reply_text(msg)
            else:
                 await query.edit_message_text(msg)

    async def process_payment_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, method: str):
        query = update.callback_query
        
        # Get active payment url
        active = context.user_data.get('active_payment')
        if not active or not active.get('url'):
            await query.edit_message_text("❌ Sesi kedaluwarsa. Silakan buat pembayaran baru.")
            return
            
        payment_url = active['url']
        
        try:
            await query.edit_message_text(f"⏳ Memproses metode pembayaran {method.upper()}...")
        except BadRequest as e:
            # Ignore if message is not modified (user double clicked)
            if "Message is not modified" not in str(e):
                raise
        
        amount = active.get('amount', 0)
        
        # Validate Minimum Amount for Bank Transfer / VA
        # Mandiri, BRI, BNI, etc usually require > 10,000
        if method in ["mandiri", "bri", "bni", "bsi", "cimb", "permata", "bjb", "bnc", "bca", "maybank", "sinarmas"]:
            try:
                if float(amount) < 10000:
                    await query.edit_message_text(
                        f"❌ *Gagal Memproses*\n\n"
                        f"Metode {method.upper()} memerlukan minimal pembayaran Rp10.000.\n"
                        f"Silakan gunakan E-Wallet (GoPay, OVO, dll) atau QRIS untuk nominal kecil.",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')]])
                    )
                    return
            except:
                pass

        # 1. SAVE TO DB FIRST (Initializing)
        # We assume active['url'] contains the unique ID (e.g. .../payment/x/UUID)
        user_id = update.effective_user.id
        donor = active.get('donor', 'Supporter')
        msg_content = active.get('message', '')
        loading_message_id = active.get('loading_message_id')
        
        # Extract ID from URL for uniqueness
        try:
            order_id = payment_url.split('/')[-1]
        except:
            order_id = f"pay_{int(time.time())}_{user_id}"

        # Save as "initializing" or "pending" immediately so we don't lose it
        payment_id = self.db.add_payment(
            user_id=user_id,
            payment_url=payment_url,
            method=method,
            amount=amount,
            message=msg_content,
            donor_name=donor,
            order_id=order_id
        )
        
        # Fetch payment details (token, qr code, etc)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: self.api.select_payment_method(payment_url, method)
        )
        
        # Handle API Error or Failure
        if not result or result.get("error") or (result.get('status') is False):
             # Log error
             print(f"[ERROR] Payment selection failed: {result}")
             
             # Mark as failed in DB so monitor doesn't pick it up
             self.db.update_payment_status(payment_id, "failed_initialization")
             
             error_msg = "Gagal memproses metode pembayaran."
             error_detail = ""
             
             if result:
                 if result.get('status') is False:
                      # Handle specific API error messages
                      if 'errors' in result and 'message' in result['errors']:
                           error_detail = result['errors']['message']
                      elif 'type_error' in result:
                           error_detail = f"Error Type: {result['type_error']}"
                 else:
                      error_msg = result.get("error", "Unknown error")

             # Translate common errors
             if "less than IDR10,000" in error_detail:
                  error_detail = "Minimal pembayaran untuk metode ini adalah Rp10.000."

             text = f"❌ *{error_msg}*\n\n"
             if error_detail:
                  text += f"Detail: {error_detail}\n\n"
             text += "Silakan coba lagi atau gunakan metode lain."
             
             await query.edit_message_text(
                 text, 
                 parse_mode='Markdown',
                 reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')]])
             )
             return

        if result and not result.get("error"):
            # 2. UPDATE DB with Details
            
            # Store specific details (token, redirect_url) to DB
            details = {}
            # Extract data from result (it might be in 'data' key or root)
            payment_data = result.get('data', result)
            
            # Check for adjusted amount (e.g. including fees)
            if 'amount' in payment_data:
                raw_amount = str(payment_data['amount']) # e.g. "IDR10,070"
                # Remove IDR and other non-digit chars
                clean_amount = re.sub(r'[^\d]', '', raw_amount)
                try:
                    details['final_amount'] = float(clean_amount)
                except:
                    pass

            if method in ["gopay", "ovo", "dana", "linkaja", "shopeepay"]:
                details['token'] = payment_data.get('token')
                details['redirect_url'] = payment_data.get('redirect_url')
            elif method == "qris":
                # For QRIS, the 'redirect_url' to check is the main payment_url
                details['redirect_url'] = payment_url
            
            if loading_message_id:
                details['loading_message_id'] = loading_message_id

            self.db.update_payment_status(payment_id, "pending", details)
            
            # ... (Rest of existing UI logic)
            
            if method in ["gopay", "ovo", "dana", "linkaja", "shopeepay"]:
                # For E-Wallets, we get a token and redirect_url from Midtrans via SociaBuzz
                midtrans_token = payment_data.get('token')
                redirect_url = payment_data.get('redirect_url')
                
                # If redirect_url is missing but we have token, we can construct the Midtrans Snap link
                # Midtrans Snap redirection URL pattern:
                if not redirect_url and midtrans_token:
                    redirect_url = f"https://app.midtrans.com/snap/v4/redirection/{midtrans_token}"
                
                keyboard = []
                # Always show the button if we have a URL (which we should now)
                if redirect_url:
                     # Dynamic button text
                     if method == "gopay":
                         btn_text = "📱 Buka Aplikasi GoJek"
                     elif method == "ovo":
                         btn_text = "📱 Buka Aplikasi OVO"
                     elif method == "dana":
                         btn_text = "📱 Buka Aplikasi DANA"
                     elif method == "shopeepay":
                         btn_text = "📱 Buka Aplikasi Shopee"
                     elif method == "linkaja":
                         btn_text = "📱 Buka Aplikasi LinkAja"
                     else:
                         btn_text = f"📱 Buka Aplikasi {method.upper()}"
                         
                     keyboard.append([InlineKeyboardButton(btn_text, url=redirect_url)])
                
                # Use 'chk_' prefix and token (or order_id) for status checking
                # We prioritize token because it's faster for E-Wallet check
                check_token = midtrans_token if midtrans_token else order_id
                keyboard.append([InlineKeyboardButton("🔄 Cek Status", callback_data=f'chk_{method}_{check_token}')])
                keyboard.append([InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')])
                
                msg_text = f"✅ *Tagihan {method.upper()} Dibuat!*\n\n"
                if redirect_url:
                    msg_text += f"Klik tombol di bawah untuk membuka aplikasi {method.upper()} dan menyelesaikan pembayaran.\n\n"
                else:
                    msg_text += f"Silakan selesaikan pembayaran melalui aplikasi {method.upper()}.\n\n"
                    
                msg_text += f"_Bot akan otomatis memberitahu jika pembayaran berhasil._"
                
                # Use send_message (delete old) if previous was photo, or edit_message_text
                if query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=msg_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text(
                        msg_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                
            elif method == "qris":
                qr_string = payment_data.get('qr_string')
                qr_image_url = payment_data.get('qr_image_url')
                redirect_url = payment_data.get('redirect_url') # The page that contains the QR
                
                # Prepare Caption
                curr_amount = details.get('final_amount', amount)
                try:
                    curr_amount_val = float(curr_amount)
                    fmt_amount = f"Rp{curr_amount_val:,.0f}".replace(",", ".")
                except:
                    fmt_amount = f"Rp{curr_amount}"

                # Expiry Time
                expiry = payment_data.get('expiration_date') or payment_data.get('expiry_date')
                expiry_dt = None
                if expiry:
                    try:
                        expiry_dt = datetime.strptime(str(expiry), "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        pass
                
                if not expiry_dt:
                    # Default to 24 hours from now
                    expiry_dt = datetime.now() + timedelta(hours=24)
                
                expiry_str = expiry_dt.strftime("%d %b %Y - %H:%M UTC+7")

                caption_text = (
                    f"⏳ *Status Pembayaran (QRIS)*\n\n"
                    f"💰 *Nominal*: {fmt_amount}\n"
                    f"📊 *Status*: Menunggu Pembayaran\n"
                    f"⏰ *Batas Waktu*: {expiry_str}\n"
                    f"💬 *Pesan*: Waiting for payment"
                )

                # If we have a direct QR string, generate image
                if qr_string or payment_data.get('payment_code'):
                    # Fallback to payment_code if qr_string is missing (some gateways use this)
                    code_to_qr = qr_string if qr_string else payment_data.get('payment_code')
                    
                    try:
                        qr = qrcode.QRCode(version=1, box_size=10, border=5)
                        qr.add_data(code_to_qr)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

                        # Add Logo if exists and enabled
                        logo_path = "assets/logo.png"
                        use_logo = self.db.get_user_setting(user_id, 'use_qris_logo', False)
                        
                        if use_logo and os.path.exists(logo_path):
                            try:
                                logo = Image.open(logo_path)
                                # Resize logo (20% of QR size)
                                qr_width, qr_height = img.size
                                logo_size = int(qr_width / 5)
                                logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                                
                                # Calculate position (center)
                                pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                                
                                # Paste logo
                                if logo.mode == 'RGBA':
                                    img.paste(logo, pos, mask=logo)
                                else:
                                    img.paste(logo, pos)
                            except Exception as e:
                                print(f"[WARNING] Failed to add logo to QR: {e}")
                        
                        bio = io.BytesIO()
                        img.save(bio, 'PNG')
                        bio.seek(0)
                        
                        keyboard = [
                             [InlineKeyboardButton("🔄 Cek Status", callback_data=f'chk_qris_dummy')]
                        ]
                        
                        if redirect_url:
                            keyboard.append([InlineKeyboardButton("🔗 Buka Link QRIS", url=redirect_url)])
                            
                        keyboard.append([InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')])
                        
                        await query.message.delete()
                        msg = await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=bio,
                            caption=caption_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                        
                        # Update DB with message_id for auto-delete
                        details['message_id'] = msg.message_id
                        self.db.update_payment_status(payment_id, "pending", details)
                    except Exception as e:
                        print(f"[ERROR] Failed to generate/send QR: {e}")
                        # Fallback to link if QR generation fails
                        if redirect_url:
                             await context.bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=f"⚠️ Gagal memuat gambar QR.\nSilakan buka link ini untuk melihat QRIS:\n{redirect_url}",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Buka Link QRIS", url=redirect_url)]])
                             )
                        else:
                             await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Gagal memuat QRIS dan tidak ada link alternatif.")
                    
                elif qr_image_url:
                     # Send photo by URL
                    keyboard = [
                         [InlineKeyboardButton("🔄 Cek Status", callback_data=f'chk_qris_dummy')]
                    ]
                    
                    if redirect_url:
                        keyboard.append([InlineKeyboardButton("🔗 Buka Link QRIS", url=redirect_url)])
                        
                    keyboard.append([InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')])
                    
                    await query.message.delete()
                    msg = await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=qr_image_url,
                        caption=caption_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                    
                    # Update DB with message_id for auto-delete
                    details['message_id'] = msg.message_id
                    self.db.update_payment_status(payment_id, "pending", details)
                else:
                    await query.edit_message_text(f"❌ Gagal mendapatkan gambar QRIS. Silakan buka link ini: {redirect_url}")

            elif method in ["mandiri", "bri", "bni", "bsi", "cimb", "permata", "bjb", "bnc", "maybank", "sinarmas"]:
                # Bank Transfer / Virtual Account (Xendit/Faspay)
                va_number = payment_data.get('payment_code') or payment_data.get('account_number') or payment_data.get('virtual_account') or payment_data.get('va_number')
                expiry = payment_data.get('expiration_date') or payment_data.get('expiry_date')
                
                if va_number:
                    curr_amount = details.get('final_amount', amount)
                    fmt_amount = f"Rp{curr_amount:,.0f}".replace(",", ".")
                    
                    # Handle Expiry Date formatting
                    expiry_dt = None
                    if expiry:
                        try:
                            # Try to parse common formats (adjust as needed based on actual API response)
                            expiry_dt = datetime.strptime(str(expiry), "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
                    
                    if not expiry_dt:
                        # Default to 24 hours from now if missing or parse failed
                        expiry_dt = datetime.now() + timedelta(hours=24)
                        
                    # Format: 10 Feb 2026 - 17:21 UTC+7
                    expiry_str = expiry_dt.strftime("%d %b %Y - %H:%M UTC+7")
                    
                    # Store VA details in user_data for status checks
                    if 'active_payment' in context.user_data:
                        context.user_data['active_payment'].update({
                            'va_number': va_number,
                            'bank_name': method.upper(),
                            'expiry_str': expiry_str
                        })

                    text = (
                        f"✅ *Tagihan {method.upper()} Dibuat!*\n\n"
                        f"Silakan transfer ke Nomor Virtual Account berikut:\n\n"
                        f"🏦 *Bank:* {method.upper()}\n"
                        f"🔢 *Nomor VA:* `{va_number}`\n"
                        f"💰 *Total:* `{fmt_amount}`\n"
                        f"⏰ *Batas Waktu:* {expiry_str}\n"
                    )
                        
                    text += f"\n_Bot akan otomatis memberitahu jika pembayaran berhasil._"
                    
                    keyboard = [
                        [InlineKeyboardButton("🔄 Cek Status", callback_data=f'chk_{method}_{order_id}')],
                        [InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')]
                    ]
                    
                    if query.message.photo:
                        await query.message.delete()
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text(
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                else:
                    # Fallback if no VA returned (maybe redirect?)
                    redirect_url = payment_data.get('redirect_url')
                    if redirect_url:
                        keyboard = [[InlineKeyboardButton("🔗 Buka Link Pembayaran", url=redirect_url)], [InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')]]
                        await query.edit_message_text(
                            f"✅ *Tagihan {method.upper()} Dibuat!*\n\nSilakan selesaikan pembayaran melalui link berikut.",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    else:
                        # Debug info
                        debug_info = str(payment_data)[:300]
                        self.db.update_payment_status(payment_id, "failed_api")
                        await query.edit_message_text(f"❌ Gagal mendapatkan nomor VA. \nData: {debug_info}\nSilakan coba lagi atau gunakan metode lain.")

            elif method == "bca":
                # BCA via Midtrans Snap
                token = None
                redirect_url = None
                
                # Check for token/url in standard response
                if 'data' in result:
                     token = result['data'].get('token')
                     redirect_url = result['data'].get('redirect_url')
                
                # Fallback to direct fields
                if not redirect_url:
                     redirect_url = result.get('redirect_url')
                
                # Try to fetch VA number if we have a token
                va_number = None
                if token:
                    va_number = self.api._get_bca_va_from_snap(token)
                
                # If we got VA number, display it like other banks
                if va_number:
                    curr_amount = details.get('final_amount', amount)
                    fmt_amount = f"Rp{curr_amount:,.0f}".replace(",", ".")
                    
                    # Set expiry to 24 hours from now
                    expiry_dt = datetime.now() + timedelta(hours=24)
                    expiry_str = expiry_dt.strftime("%d %b %Y - %H:%M UTC+7")
                    
                    # Store VA details in user_data for status checks
                    if 'active_payment' in context.user_data:
                        context.user_data['active_payment'].update({
                            'va_number': va_number,
                            'bank_name': 'BCA',
                            'expiry_str': expiry_str
                        })

                    text = (
                        f"✅ *Tagihan BCA Dibuat!*\n\n"
                        f"Silakan transfer ke Nomor Virtual Account berikut:\n\n"
                        f"🏦 *Bank:* BCA\n"
                        f"🔢 *Nomor VA:* `{va_number}`\n"
                        f"💰 *Total:* `{fmt_amount}`\n"
                        f"⏰ *Batas Waktu:* {expiry_str}\n"
                    )
                    
                    text += f"\n_Bot akan otomatis memberitahu jika pembayaran berhasil._"
                    
                    keyboard = [
                        [InlineKeyboardButton("🔄 Cek Status", callback_data=f'chk_bca_{order_id}')],
                        [InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')]
                    ]
                    
                    if query.message.photo:
                        await query.message.delete()
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text(
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                
                # Fallback to link if VA fetch fails
                elif redirect_url:
                    text = (
                        f"✅ *Tagihan BCA Dibuat!*\n\n"
                        f"Silakan selesaikan pembayaran melalui link di bawah ini.\n"
                        f"Nomor Virtual Account akan muncul setelah membuka link.\n\n"
                        f"💰 *Total:* Rp{amount:,.0f}\n"
                    )
                    
                    keyboard = [
                         [InlineKeyboardButton("🔗 Buka Pembayaran (Snap)", url=redirect_url)],
                         [InlineKeyboardButton("🔄 Cek Status", callback_data=f'chk_bca_{order_id}')],
                         [InlineKeyboardButton("🔙 Ganti Metode", callback_data='change_method')]
                    ]
                    
                    if query.message.photo:
                        await query.message.delete()
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text(
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                else:
                    await query.edit_message_text("❌ Gagal mendapatkan link pembayaran BCA.")

        else:
             error_msg = result.get("error", "Unknown error") if result else "No response from API"
             self.db.update_payment_status(payment_id, "failed_api")
             await query.edit_message_text(f"❌ Gagal memproses metode pembayaran.\nDetail: {error_msg}")

    async def check_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_logged_in = self.auth.check_session()
        status_text = "✅ *Terhubung*" if is_logged_in else "❌ *Tidak Terhubung*"
        
        details = (
            f"🔍 *Status Sistem*\n\n"
            f"Sesi: {status_text}\n"
            f"Cookies: {'Dimuat' if self.auth.session.cookies else 'Kosong'}\n"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Kembali", callback_data='back_to_menu')]]
        await update.callback_query.edit_message_text(
            text=details,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def view_transactions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        
        # Get page number from callback data
        page = 1
        if query.data.startswith('view_transactions_page_'):
            try:
                page = int(query.data.split('_')[-1])
            except ValueError:
                page = 1
        
        # Try to read from transactions.json first (fastest)
        data = None
        
        if os.path.exists("transactions.json"):
            try:
                with open("transactions.json", "r", encoding='utf-8') as f:
                    data = json.load(f)
            except:
                pass
        
        # If no cache or forced refresh needed (can implement force later), use API if logged in
        # But for now, we rely on background task or existing session
        
        if not data:
            # Fallback to direct fetch if possible
            if self.auth.check_session():
                 balance = self.tm.get_balance_info()
                 history = self.tm.get_history()
                 pending = self.tm.get_pending_transactions()
                 data = {
                     "balance_info": balance,
                     "history": history,
                     "pending": pending
                 }
            else:
                 await query.edit_message_text("❌ Tidak ada data tersedia. Silakan login via CLI terlebih dahulu atau tunggu monitor background.")
                 return

        # Parse Data
        balance_val = 0
        total_earnings = 0
        if 'balance_info' in data and data['balance_info'].get('success'):
            balance_val = data['balance_info'].get('balance', 0)
            # total_earnings = data['balance_info'].get('total_saldo', 0) # Overridden below
            
        history_list = []
        if 'history' in data and data['history'].get('success'):
             history_list = data['history'].get('transactions', [])
             
        # Calculate total earnings from history strings (User Request)
        calculated_earnings = 0
        for item in history_list:
            if isinstance(item, dict):
                amount_str = item.get('amount', '')
                if amount_str:
                    # Parse "+Rp9.500" or "-Rp19.000"
                    clean = amount_str.strip()
                    try:
                        # Remove Rp and .
                        val_str = clean.replace('Rp', '').replace('.', '').replace('+', '').replace('-', '').strip()
                        if val_str.isdigit():
                            val = int(val_str)
                            # Only add positive transactions to "Total Pendapatan"
                            if clean.startswith('+') or (not clean.startswith('-') and 'Rp' in clean): 
                                calculated_earnings += val
                    except:
                        pass
        
        total_earnings = calculated_earnings

        pending_list = []
        if 'pending' in data and data['pending'].get('success'):
             pending_list = data['pending'].get('data', [])

        # Build Message
        text = f"📊 *Laporan Keuangan*\n\n"
        
        # 1. Balance
        text += f"💰 *Saldo Aktif*: `Rp{balance_val:,}`\n"
        text += f"📈 *Total Pendapatan*: `Rp{total_earnings:,}`\n"
        text += "-" * 20 + "\n"
        
        # 2. Pending Transactions (if any)
        if pending_list:
            text += "⏳ *Transaksi Pending*\n"
            for item in pending_list[:5]: # Limit 5
                 if isinstance(item, dict):
                     label = item.get('text', str(item))
                     text += f"• {label}\n"
            text += "-" * 20 + "\n"
            
        # 3. History with Pagination
        text += "📜 *Riwayat Transaksi*\n"
        
        items_per_page = 10
        total_items = len(history_list)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        # Ensure page is within bounds
        if page < 1: page = 1
        if page > total_pages and total_pages > 0: page = total_pages
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_page_items = history_list[start_idx:end_idx]
        
        if not history_list:
            text += "_Tidak ada transaksi terbaru._\n"
        else:
            for i, item in enumerate(current_page_items):
                idx = start_idx + i + 1
                if isinstance(item, dict):
                    title = item.get('title', 'Unknown')
                    date = item.get('date', '')
                    amount = item.get('amount', '')
                    # Fallback for raw text
                    if title == "Raw Data":
                         text += f"• {item.get('text', '')}\n\n"
                    else:
                         text += f"*{idx}. {title}*\n   📅 {date}\n   💰 {amount}\n\n"
                else:
                    text += f"• {item}\n"
            
            if total_pages > 1:
                text += f"_Halaman {page} dari {total_pages}_\n"
        
        # Add timestamp if available
        if 'timestamp' in data:
            import datetime
            ts = datetime.datetime.fromtimestamp(data['timestamp']).strftime('%d-%m-%Y %H:%M:%S')
            text += f"\n_Terakhir Diperbarui: {ts}_"

        # Pagination Buttons
        keyboard = []
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f'view_transactions_page_{page-1}'))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f'view_transactions_page_{page+1}'))
            keyboard.append(nav_buttons)
            
        keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data='back_to_menu')])
        
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    pass
                else:
                    raise

    def _escape_markdown(self, text):
        """Helper to escape markdown special characters."""
        if not text:
            return ""
        # Escape characters that have special meaning in Markdown (v1)
        # In Markdown v1: _ * ` [ ]
        # We need to escape them to avoid parsing errors
        escaped = str(text).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[').replace(']', '\\]')
        return escaped

    async def view_user_transactions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        user_id = user.id
        
        # Get page number from callback data
        page = 1
        if query.data.startswith('user_transactions_page_'):
            try:
                page = int(query.data.split('_')[-1])
            except ValueError:
                page = 1
        
        # Fetch user history from DB
        # Fetching up to 1000 for pagination
        history_list = self.db.get_user_history(user_id, limit=1000)
        
        # Calculate totals
        total_spent = self.db.get_user_success_total(user_id)
        formatted_total = f"Rp{total_spent:,.0f}".replace(",", ".")
        
        # Escape user_id and total in case they contain weird chars (unlikely for ID but good practice)
        safe_user_id = self._escape_markdown(user_id)
        safe_total = self._escape_markdown(formatted_total)

        text = (
            f"👤 *Riwayat Transaksi Saya*\n"
            f"ID: `{safe_user_id}`\n"
            f"💰 Total Transaksi Berhasil: `{safe_total}`\n\n"
        )
        
        # Pagination Logic
        items_per_page = 10
        total_items = len(history_list)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        # Ensure page is within bounds
        if page < 1: page = 1
        if page > total_pages and total_pages > 0: page = total_pages
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_page_items = history_list[start_idx:end_idx]
        
        if not history_list:
            text += "_Belum ada riwayat transaksi._\n"
        else:
            for i, p in enumerate(current_page_items):
                idx = start_idx + i + 1
                try:
                    dt = datetime.fromisoformat(p["created_at"])
                    date_str = dt.strftime("%d %b %Y - %H:%M")
                except:
                    date_str = "-"
                
                try:
                    amount_val = float(p['amount'])
                    fmt_amount = f"Rp{amount_val:,.0f}".replace(",", ".")
                except:
                    fmt_amount = f"Rp{p['amount']}"
                
                status_icon = "✅" if p['status'] == 'success' else "⏳" if p['status'] == 'pending' else "❌"
                
                method_name = p.get('method', 'Unknown')
                
                # Escape dynamic fields!
                safe_date = self._escape_markdown(date_str)
                safe_amount = self._escape_markdown(fmt_amount)
                safe_method = self._escape_markdown(method_name)
                
                # Format: 1. ✅ 10/02 14:30 - Rp50.000 (QRIS)
                text += f"{idx}. {status_icon} `{safe_date}` - *{safe_amount}* ({safe_method})\n"
            
            if total_pages > 1:
                text += f"\n_Halaman {page} dari {total_pages}_\n"

        # Pagination Buttons
        keyboard = []
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f'user_transactions_page_{page-1}'))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f'user_transactions_page_{page+1}'))
            keyboard.append(nav_buttons)
            
        keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data='back_to_menu')])
        
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    pass
                else:
                    raise

    async def view_withdrawals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        
        # 1. Get Balance
        balance_val = 0
        try:
            # Try to get from transactions.json first for speed
            if os.path.exists("transactions.json"):
                with open("transactions.json", "r", encoding='utf-8') as f:
                    data = json.load(f)
                    if 'balance_info' in data and data['balance_info'].get('success'):
                         balance_val = data['balance_info'].get('balance', 0)
        except:
            pass
            
        # If 0, maybe try to refresh if session exists (optional, skipping for speed)
        
        formatted_balance = f"Rp{balance_val:,}".replace(",", ".")

        # 2. Build UI
        text = (
            f"💰 *Pencairan Dana*\n\n"
            f"Saldo: *{formatted_balance}*\n\n"
            f"Cairkan ke:"
        )
        
        # 3. Withdrawal Methods Buttons
        # Simulating the radio button UI with direct selection buttons
        keyboard = [
            [InlineKeyboardButton("🏦 Transfer Bank", callback_data='withdraw_select_bank')],
            [InlineKeyboardButton("� GoPay", callback_data='withdraw_select_gopay')],
            [InlineKeyboardButton("� DANA", callback_data='withdraw_select_dana')],
            [InlineKeyboardButton("🟣 OVO", callback_data='withdraw_select_ovo')],
            [InlineKeyboardButton("🟠 ShopeePay", callback_data='withdraw_select_shopeepay')],
            [InlineKeyboardButton("🔴 LinkAja", callback_data='withdraw_select_linkaja')],
            [InlineKeyboardButton("🔙 Kembali", callback_data='back_to_menu')]
        ]
        
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

    async def _handle_withdrawal_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, method_name, method_code):
        query = update.callback_query
        
        # Mock details based on the image provided by user
        fee = "Rp0"
        if method_code == "dana":
             fee = "Rp100"
        elif method_code == "bank":
             fee = "Rp3.000" # Common fee
        
        text = (
            f"💰 *Pencairan Dana*\n\n"
            f"Metode Dipilih: *{method_name}*\n"
            f"Biaya penarikan: {fee}\n\n"
            f"_Klik 'Lanjut' untuk memproses pencairan._"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Lanjut", callback_data=f'withdraw_proceed_{method_code}')],
            [InlineKeyboardButton("🔙 Ganti Metode", callback_data='withdrawals')]
        ]
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_data = context.user_data
        
        # 0. Handle Admin Info Update Input
        if user_data.get('setting_state') == 'waiting_for_info_text':
            if not self._is_authorized(update):
                 del user_data['setting_state']
                 return
            
            info_text = update.message.text
            user_data['pending_info_text'] = info_text
            del user_data['setting_state']
            
            preview_text = (
                f"📢 *Preview Informasi Bot*\n"
                f"--------------------------\n"
                f"{info_text}\n"
                f"--------------------------\n\n"
                f"Apakah Anda yakin ingin menyimpan dan membroadcast pesan ini?"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Ya, Simpan & Broadcast", callback_data='confirm_broadcast_info')],
                [InlineKeyboardButton("❌ Batal", callback_data='cancel_broadcast')]
            ]
            
            await update.message.reply_text(
                preview_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # 1. Handle Settings Input (Default Target)
        if user_data.get('setting_state') == 'waiting_for_target':
            # Ensure only authorized users can set this (double check, though state should guard)
            if not self._is_authorized(update):
                 del user_data['setting_state']
                 return

            target = update.message.text.strip()
            # Basic validation
            if " " in target or len(target) < 3:
                 await update.message.reply_text("❌ Username tidak valid. Gunakan satu kata tanpa spasi, minimal 3 karakter.")
                 return
                 
            self.db.set_global_setting("default_target", target)
            del user_data['setting_state']
            
            await update.message.reply_text(
                f"✅ Global default target berhasil diset ke: *{target}*\n\n"
                f"Sekarang semua user bisa menggunakan:\n`/pay 10000 pesan`",
                parse_mode='Markdown'
            )
            return

        # 2. Handle Payment Creation Input
        if user_data.get('payment_state') == 'waiting_for_amount':
            text = update.message.text.strip()
            
            # Delete user input message to keep chat clean
            try:
                await update.message.delete()
            except Exception:
                pass
            
            # Validate amount
            try:
                # Remove Rp, dots, commas
                clean_text = re.sub(r'[^\d]', '', text)
                amount = int(clean_text)
                
                if amount <= 0:
                    await update.message.reply_text("❌ Jumlah harus lebih besar dari 0.")
                    return
                
                # Minimum amount check (e.g. 1000 or 10000 depending on gateway, let's say 1000)
                if amount < 1000:
                     await update.message.reply_text("❌ Minimal pembayaran adalah Rp1.000.")
                     return

                # Get default target
                default_target = self.db.get_global_setting("default_target")
                if not default_target:
                    await update.message.reply_text("⚠️ Sistem belum siap (Default Target belum diset oleh Admin). Silakan hubungi admin.")
                    return
                
                # Delete the prompt message if exists
                prompt_msg_id = user_data.get('payment_prompt_message_id')
                if prompt_msg_id:
                    try:
                        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prompt_msg_id)
                    except Exception:
                        pass
                    # Cleanup
                    if 'payment_prompt_message_id' in user_data:
                        del user_data['payment_prompt_message_id']

                # Clear state
                del user_data['payment_state']
                
                # Execute Payment Creation
                # We use default message "Support"
                await self._execute_payment_creation(update, context, default_target, amount, "Support")
                
            except ValueError:
                await update.message.reply_text("❌ Mohon masukkan angka yang valid.")
            
            return

        # 3. Handle Withdrawal Input
        if 'withdrawal_state' not in user_data:
            return # Not in withdrawal mode
            
        state = user_data['withdrawal_state']
        method_code = state['method_code']
        method_name = state['method_name']
        balance = state['balance']
        
        text = update.message.text.strip()
        
        # Validate amount
        try:
            # Remove Rp, dots, commas
            clean_text = re.sub(r'[^\d]', '', text)
            amount = int(clean_text)
            
            if amount <= 0:
                await update.message.reply_text("❌ Jumlah harus lebih besar dari 0.")
                return
                
            if amount > balance:
                await update.message.reply_text(
                    f"❌ Saldo tidak mencukupi.\nSaldo Anda: Rp{balance:,}".replace(",", ".") + 
                    f"\nJumlah diminta: Rp{amount:,}".replace(",", ".")
                )
                return
                
            # Calculate Fee
            fee = 0
            if method_code == "dana":
                fee = 100
            elif method_code == "bank":
                fee = 3000
                
            total_deduction = amount # Usually fee is deducted from amount or added? 
            # SociaBuzz usually deducts fee from the amount sent, or adds it?
            # Let's assume amount is what user wants to receive, so we check if balance covers amount + fee?
            # Actually, usually you withdraw X, and you receive X - fee.
            # So if I withdraw 10000, I receive 9900 (Dana).
            # So the input amount is the withdrawal amount.
            
            receive_amount = amount - fee
            if receive_amount <= 0:
                 await update.message.reply_text("❌ Jumlah terlalu kecil setelah dipotong biaya admin.")
                 return

            # Confirm
            msg = (
                f"✅ *Konfirmasi Pencairan*\n\n"
                f"Metode: {method_name}\n"
                f"Jumlah Penarikan: Rp{amount:,}\n"
                f"Biaya Admin: Rp{fee:,}\n"
                f"Estimasi Diterima: Rp{receive_amount:,}\n\n"
                f"Apakah Anda yakin?"
            ).replace(",", ".")
            
            keyboard = [
                [InlineKeyboardButton("✅ Ya, Cairkan", callback_data=f'withdraw_confirm_{method_code}_{amount}')],
                [InlineKeyboardButton("❌ Batal", callback_data='withdrawals')]
            ]
            
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            
            # Clear state to prevent double handling (or keep it if we want to allow retry?)
            # Ideally keep it until confirmed or cancelled, but for simplicity let's rely on buttons now.
            del context.user_data['withdrawal_state']
            
        except ValueError:
            await update.message.reply_text("❌ Mohon masukkan angka yang valid.")

    async def create_payment_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"\n[DEBUG_FLOW] 🚀 Command /pay received from user {update.effective_user.id}")
        
        # Check for existing active payment
        if 'active_payment' in context.user_data:
            active = context.user_data['active_payment']
            # Optionally check if expired (e.g. check active['timestamp'])
            # For now, just block and offer to cancel/view
            
            keyboard = [
                [InlineKeyboardButton("👀 Lihat Pembayaran Pending", callback_data='change_method')], # Re-using change_method to view selection
                [InlineKeyboardButton("❌ Batalkan Pembayaran Pending", callback_data='cancel_payment')]
            ]
            await update.message.reply_text(
                "⚠️ Anda memiliki pembayaran yang sedang diproses.\nSilakan selesaikan atau batalkan sebelum membuat yang baru.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Syntax: /pay username amount message
        # Or: /pay amount message (if default target is set)
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Penggunaan: /pay <username> <jumlah> [pesan]")
            return

        username = None
        amount = None
        message = "Support"
        
        # Use Global Setting
        default_target = self.db.get_global_setting("default_target")
        
        # Try to parse as standard format: /pay <username> <amount> ...
        if len(args) >= 2:
            try:
                test_amount = int(args[1])
                # If success, use standard format
                username = args[0]
                amount = test_amount
                message = " ".join(args[2:]) if len(args) > 2 else "Support"
            except ValueError:
                pass # Not standard format
        
        # If standard parsing failed, try default target format: /pay <amount> ...
        if amount is None:
            if default_target:
                try:
                    amount = int(args[0])
                    username = default_target
                    message = " ".join(args[1:]) if len(args) > 1 else "Support"
                except ValueError:
                    pass
            
        if amount is None or username is None:
             print(f"[DEBUG_FLOW] ❌ Invalid /pay format. Args: {args}")
             if default_target:
                 await update.message.reply_text("Format salah.\n\nDengan default target:\n/pay <jumlah> [pesan]\n\nManual:\n/pay <username> <jumlah> [pesan]")
             else:
                 await update.message.reply_text("Penggunaan: /pay <username> <jumlah> [pesan]\nJumlah harus berupa angka.")
             return

        print(f"[DEBUG_FLOW] ✅ Payment request valid: Username={username}, Amount={amount}, Message={message}")
        print(f"[DEBUG_FLOW] 🔄 Calling API create_support_payment...")

        await self._execute_payment_creation(update, context, username, amount, message)

    async def _execute_payment_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, amount: int, message: str):
        # loading_msg = await update.message.reply_text(f"⏳ Membuat link pembayaran untuk {username} (Rp{amount})...")
        loading_message_id = None
        
        # We need to run blocking code in a separate thread
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: self.api.create_support_payment(
                username, amount, message, "supporter@example.com", "Supporter"
            )
        )
        
        # Check for different response structures
        payment_url = None
        error_message = None
        
        if result:
            if 'content' in result and 'redirect' in result['content']:
                payment_url = result['content']['redirect']
            elif 'data' in result and 'url' in result['data']:
                payment_url = result['data']['url']
            elif 'validates' in result:
                # Handle validation errors
                validates = result['validates']
                errors = []
                for field, msg in validates.items():
                    if msg:
                        errors.append(f"- {field.capitalize()}: {msg}")
                if errors:
                    error_message = "❌ Kesalahan Validasi:\n" + "\n".join(errors)
        
        if payment_url:
            # Store URL for next step
            context.user_data['pending_payment_url'] = payment_url
            
            # Prepare details
            now = datetime.now()
            date_str = now.strftime("%d %b %Y - %H:%M")
            fmt_amount = f"Rp{amount:,.0f}".replace(",", ".")
            
            # Set active payment state
            context.user_data['active_payment'] = {
                'url': payment_url,
                'created_at': now.timestamp(), # Use wall clock timestamp
                'date_str': date_str,
                'loading_message_id': loading_message_id,
                'amount': amount,
                'donor': "Supporter",
                'message': message
            }
            
            # Create keyboard for payment methods
            keyboard = [
                # E-Wallet & QRIS Section
                [InlineKeyboardButton("💳 E-WALLET & QRIS", callback_data='dummy_header_ewallet')],
                [
                    InlineKeyboardButton("🟢 GoPay", callback_data='pay_gopay')
                ],
                [
                    InlineKeyboardButton("📱 QRIS", callback_data='pay_qris')
                ],
                # Bank Section
                [InlineKeyboardButton("🏦 Transfer Bank", callback_data='dummy_header_bank')],
                [
                    InlineKeyboardButton("🏦 Mandiri", callback_data='pay_mandiri'),
                    InlineKeyboardButton("🏦 BRI", callback_data='pay_bri')
                ],
                [
                    InlineKeyboardButton("🏦 BNI", callback_data='pay_bni'),
                    InlineKeyboardButton("🏦 BSI", callback_data='pay_bsi'),
                    InlineKeyboardButton("🏦 CIMB", callback_data='pay_cimb')
                ],
                [
                    InlineKeyboardButton("🏦 Permata", callback_data='pay_permata'),
                    InlineKeyboardButton("🏦 BJB", callback_data='pay_bjb'),
                    InlineKeyboardButton("🏦 BNC", callback_data='pay_bnc')
                ],
                [
                    InlineKeyboardButton("🏦 BCA", callback_data='pay_bca'),
                    InlineKeyboardButton("🏦 Maybank", callback_data='pay_maybank'),
                    InlineKeyboardButton("🏦 Sinarmas", callback_data='pay_sinarmas')
                ],
                [
                    InlineKeyboardButton("❌ Batalkan Pembayaran", callback_data='cancel_payment')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                f"🧾 *Detail Pembayaran*\n\n"
                f"🕒 *Waktu:* {date_str}\n"
                f"💰 *Nominal:* {fmt_amount}\n\n"
                f"✅ Link Pembayaran Dibuat!\nPilih metode pembayaran untuk melanjutkan:"
            )
            
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        elif error_message:
            await update.message.reply_text(error_message)
        else:
            await update.message.reply_text(f"❌ Gagal membuat link pembayaran.\nRespon: {result}")

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
            
        # Global setting for default target
        default_target = self.db.get_global_setting("default_target")
        
        target_display = default_target if default_target else "(Belum diset)"
        
        keyboard = [
            [InlineKeyboardButton("📝 Set Global Target", callback_data='set_default_target')],
            [InlineKeyboardButton("🔙 Kembali", callback_data='back_to_menu')]
        ]
        
        await update.message.reply_text(
            f"⚙️ *Pengaturan Bot*\n\n"
            f"👤 Global Default Target: `{target_display}`\n\n"
            f"Target ini berlaku untuk SEMUA user yang menjalankan `/pay` tanpa username.\n"
            f"Contoh: `/pay 50000` akan otomatis mengarah ke `{target_display}`.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        
        current_status = self.api.debug_mode
        new_status = not current_status
        self.api.set_debug_mode(new_status)
        
        status_text = "AKTIF" if new_status else "NON-AKTIF"
        await update.message.reply_text(f"🛠️ Debug Mode: *{status_text}*\nLog disimpan di `api_debug.log`.", parse_mode='Markdown')

    async def check_channel_membership(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        required_channel = Config.REQUIRED_CHANNEL_USERNAME
        if not required_channel:
            return True

        user_id = update.effective_user.id
        try:
            member = await context.bot.get_chat_member(chat_id=required_channel, user_id=user_id)
            # Check if user is a member (creator, administrator, member, restricted)
            # 'left' means they are not a member. 'kicked' means banned.
            if member.status in ['left', 'kicked']:
                await self.show_force_subscribe_message(update, required_channel)
                return False
            return True
        except BadRequest as e:
            # If bot is not admin or channel not found, log warning but allow access
            # to avoid blocking users due to misconfiguration
            logging.warning(f"Could not check membership for {required_channel}: {e}")
            return True
        except Exception as e:
            logging.error(f"Unexpected error checking membership: {e}")
            return True

    async def show_force_subscribe_message(self, update: Update, channel_username: str):
        # Extract channel link (remove @ for url)
        channel_link = f"https://t.me/{channel_username.replace('@', '')}"
        
        text = (
            "🔒 *Akses Terbatas*\n\n"
            "Untuk menggunakan bot ini, Anda wajib bergabung ke channel kami terlebih dahulu.\n\n"
            "Silakan klik tombol di bawah untuk bergabung, lalu klik 'Cek Status' untuk melanjutkan."
        )
        
        keyboard = [
            [InlineKeyboardButton("📢 Gabung Channel", url=channel_link)],
            [InlineKeyboardButton("✅ Cek Status", callback_data='check_subscription')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            try:
                # Use answer to stop loading animation on button click
                # await update.callback_query.answer() # Called by caller usually, but safe to call again
                await update.callback_query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except BadRequest:
                 # If editing fails, send new
                 await update.callback_query.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                 )
        else:
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    def _is_authorized(self, update: Update):
        user_id = update.effective_user.id
        # If admin ID is set, check it. Otherwise allow all (dev mode)
        if Config.TELEGRAM_ADMIN_ID and str(user_id) != str(Config.TELEGRAM_ADMIN_ID):
             return False
        return True

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and send a telegram message to notify the developer."""
        logging.error(msg="Exception while handling an update:", exc_info=context.error)
        
        # Send error message to user if it's a telegram update
        if isinstance(update, Update) and update.effective_message:
            text = "❌ Terjadi kesalahan internal pada bot."
            try:
                await update.effective_message.reply_text(text)
            except:
                pass

    async def post_init(self, application: Application):
        """Post-initialization hook to start background tasks."""
        self.monitoring_task = asyncio.create_task(self.monitor_pending_payments(application))

    async def post_shutdown(self, application: Application):
        """Post-shutdown hook to stop background tasks."""
        if self.monitoring_task and not self.monitoring_task.done():
            print("🛑 Stopping background monitoring task...")
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            print("✅ Background monitoring task stopped.")

    def run(self):
        if not Config.validate():
            print("Please configure your .env file first.")
            return

        application = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).post_init(self.post_init).post_shutdown(self.post_shutdown).build()
        
        application.add_handler(CommandHandler('start', self.start))
        application.add_handler(CommandHandler('pay', self.create_payment_command))
        application.add_handler(CommandHandler('settings', self.settings_command))
        application.add_handler(CommandHandler('debug', self.debug_command))
        application.add_handler(CallbackQueryHandler(self.button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input))
        application.add_error_handler(self.error_handler)
        
        print("🤖 Telegram Bot is running...")
        application.run_polling()

if __name__ == '__main__':
    print("🚀 Starting SocialBuzzBot...")
    try:
        bot = SocialBuzzBot()
        bot.run()
    except Exception as e:
        print(f"❌ Critical Error: {e}")
        import traceback
        traceback.print_exc()
