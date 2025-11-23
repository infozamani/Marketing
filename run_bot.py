from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import EmailMessage
from bot_app.models import ChatLog
import telebot
import google.generativeai as genai
import re
# این خط را به بالای فایل (زیر import telebot) اضافه کنید



# --- تنظیمات ---
# توکن و API KEY خود را اینجا چک کنید
TELEGRAM_TOKEN = "8286709618:AAHBhc_TbGBDtOEGiw1exhxQD8HPn443Epc"
GOOGLE_API_KEY = "AIzaSyBuB8Erbmztj0IOhH_ursOcpqcXIete7nk"
TARGET_EMAIL = "fariborz499@gmail.com"
# تنظیم پروکسی (این پورت 10809 معمولا برای v2ray است. اگر کار نکرد 1080 یا 2081 را تست کنید)
# اگر از سایفون یا چیز دیگری استفاده می‌کنید پورتش فرق دارد



class Command(BaseCommand):
    help = 'Runs the Telegram Bot with Email capabilities'

    def handle(self, *args, **kwargs):
        # اتصال به سرویس‌ها
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        self.stdout.write(self.style.SUCCESS('Bot is running and ready...'))

        # ---------------------------------------------------------
        # توابع کمکی (Helper Functions)
        # ---------------------------------------------------------

        def get_user_name(message):
            """این تابع بهترین نام ممکن را برای کاربر پیدا می‌کند"""
            if message.chat.username:
                return f"@{message.chat.username}"
            elif message.chat.first_name:
                return message.chat.first_name
            else:
                return "Unknown User"

        def send_email_custom(to_email, subject, body, file_data=None, file_name=None, mime_type=None):
            """تابع اصلی ارسال ایمیل"""
            try:
                email = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=settings.EMAIL_HOST_USER,
                    to=[to_email],
                )
                if file_data:
                    email.attach(file_name, file_data, mime_type)
                
                email.send()
                return True
            except Exception as e:
                print(f"Email Error: {e}")
                return False

        def extract_email_and_text(text):
            """تشخیص ایمیل و متن جداگانه"""
            if not text: return None, None
            # الگوی Regex برای پیدا کردن ایمیل در ابتدای پیام
            pattern = r'^([\w\.-]+@[\w\.-]+\.\w+)\s*:?\s*(.*)'
            match = re.match(pattern, text, re.DOTALL)
            if match:
                return match.group(1), match.group(2)
            return None, None

        # ---------------------------------------------------------
        # 1. هندلر متن (Text Handler)
        # ---------------------------------------------------------
        @bot.message_handler(content_types=['text'])
        def handle_text(message):
            user_name = get_user_name(message)
            user_text = message.text

            # الف) بررسی درخواست ایمیل
            target_email, email_body = extract_email_and_text(user_text)
            
            if target_email:
                bot.reply_to(message, f"📧 در حال ارسال ایمیل متنی به {target_email}...")
                
                if not email_body:
                    email_body = "این پیام از طریق ربات تلگرام ارسال شده است."

                success = send_email_custom(
                    to_email=target_email,
                    subject=f"پیام متنی از طرف: {user_name}",
                    body=email_body
                )
                
                if success:
                    bot.reply_to(message, "✅ ایمیل ارسال شد.")
                    log_msg = f"Emailed to {target_email}"
                    m_type = 'email_text'
                else:
                    bot.reply_to(message, "❌ خطا در ارسال ایمیل.")
                    log_msg = "Email Failed"
                    m_type = 'error'

                # ذخیره در دیتابیس
                ChatLog.objects.create(
                    user_id=str(message.chat.id),
                    username=user_name,
                    message_type=m_type,
                    user_input=user_text,
                    bot_response=log_msg
                )
                return

            # ب) هوش مصنوعی (جمینی)
            try:
                response = model.generate_content(user_text)
                bot.reply_to(message, response.text)
                
                ChatLog.objects.create(
                    user_id=str(message.chat.id),
                    username=user_name,
                    message_type='text',
                    user_input=user_text,
                    bot_response=response.text
                )
                print(f"Saved text from {user_name}")

            except Exception as e:
                print(f"Error: {e}")
                bot.reply_to(message, "خطایی رخ داد.")

        # ---------------------------------------------------------
        # 2. هندلر عکس (Photo Handler)
        # ---------------------------------------------------------
        @bot.message_handler(content_types=['photo'])
        def handle_photo(message):
            user_name = get_user_name(message)
            caption = message.caption or ""
            
            # الف) بررسی درخواست ایمیل در کپشن
            target_email, body_text = extract_email_and_text(caption)

            if target_email:
                msg = bot.reply_to(message, f"📧 در حال ایمیل کردن عکس به {target_email}...")
                
                # دانلود عکس
                file_info = bot.get_file(message.photo[-1].file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                
                success = send_email_custom(
                    to_email=target_email,
                    subject=f"عکس ارسالی از: {user_name}",
                    body=body_text if body_text else "یک تصویر پیوست شد.",
                    file_data=downloaded_file,
                    file_name="photo.jpg",
                    mime_type="image/jpeg"
                )
                
                if success:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="✅ عکس ایمیل شد.")
                    
                    ChatLog.objects.create(
                        user_id=str(message.chat.id),
                        username=user_name,
                        message_type='email_photo',
                        user_input="[Photo sent via Email]",
                        bot_response=f"Sent to {target_email}"
                    )
                else:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="❌ خطا در ارسال.")
                return

            # ب) تحلیل تصویر با جمینی
            try:
                msg = bot.reply_to(message, "🖼 در حال تحلیل تصویر...")
                
                file_info = bot.get_file(message.photo[-1].file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                
                image_parts = [{"mime_type": "image/jpeg", "data": downloaded_file}]
                
                prompt = caption if caption else "توضیح بده در این تصویر چه می‌بینی؟"
                response = model.generate_content([prompt, image_parts[0]])
                
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=response.text)

                ChatLog.objects.create(
                    user_id=str(message.chat.id),
                    username=user_name,
                    message_type='photo_analysis',
                    user_input="[Photo Analysis Request]",
                    bot_response=response.text
                )
            except Exception as e:
                print(e)
                bot.reply_to(message, "خطا در تحلیل تصویر.")

        # ---------------------------------------------------------
        # 3. هندلر فایل صوتی (Voice Handler)
        # ---------------------------------------------------------
        @bot.message_handler(content_types=['voice'])
        def handle_voice(message):
            user_name = get_user_name(message)
            caption = message.caption or ""
            
            # الف) بررسی درخواست ایمیل (اگر ویس فوروارد شده و کپشن داشت)
            # نکته: ویس‌های عادی معمولا کپشن ندارند، اما اگر فوروارد کنید دارند.
            target_email, body_text = extract_email_and_text(caption)

            # دانلود فایل صوتی (برای هر دو حالت لازم است)
            try:
                file_info = bot.get_file(message.voice.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
            except Exception as e:
                bot.reply_to(message, "خطا در دانلود فایل صوتی.")
                return

            if target_email:
                msg = bot.reply_to(message, f"📧 در حال ایمیل کردن ویس به {target_email}...")
                
                success = send_email_custom(
                    to_email=target_email,
                    subject=f"پیام صوتی از: {user_name}",
                    body=body_text if body_text else "فایل صوتی پیوست شد.",
                    file_data=downloaded_file,
                    file_name="voice_message.ogg",
                    mime_type="audio/ogg"
                )
                
                if success:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="✅ ویس ایمیل شد.")
                    
                    ChatLog.objects.create(
                        user_id=str(message.chat.id),
                        username=user_name,
                        message_type='email_voice',
                        user_input="[Voice sent via Email]",
                        bot_response=f"Sent to {target_email}"
                    )
                else:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="❌ خطا در ارسال.")
                return

            # ب) تبدیل صوت به متن با جمینی (حالت پیش‌فرض)
            try:
                msg = bot.reply_to(message, "🎤 در حال تبدیل صوت به متن...")
                
                audio_parts = [{"mime_type": "audio/ogg", "data": downloaded_file}]
                
                response = model.generate_content(["لطفاً این فایل صوتی را دقیق به متن فارسی تبدیل کن:", audio_parts[0]])
                
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=response.text)

                ChatLog.objects.create(
                    user_id=str(message.chat.id),
                    username=user_name,
                    message_type='voice_transcribe',
                    user_input="[Voice Transcription Request]",
                    bot_response=response.text
                )
            except Exception as e:
                print(e)
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="خطا در تبدیل صوت.")

        # روشن نگه داشتن ربات
        bot.infinity_polling()