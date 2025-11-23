from django.core.management.base import BaseCommand
from marketing_bot.models import ProductContent, Order
from django.core.files.base import ContentFile
import telebot
from telebot import types
import google.generativeai as genai
import requests
import json
import os
import time  # [NEW] برای وقفه بین تلاش‌ها

# --- پاکسازی تنظیمات پروکسی ---
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# --- تنظیمات ---
TELEGRAM_TOKEN = "8286709618:AAHBhc_TbGBDtOEGiw1exhxQD8HPn443Epc"
GOOGLE_API_KEY = "AIzaSyBuB8Erbmztj0IOhH_ursOcpqcXIete7nk"
ADMIN_ID = "YOUR_TELEGRAM_NUMERIC_ID" 

class Command(BaseCommand):
    help = 'Runs the Super Bot (With Robust Image Download)'

    def handle(self, *args, **kwargs):
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        self.stdout.write(self.style.SUCCESS('🚀 Super Bot Started! (Robust Mode)'))

        # =========================================================
        # بخش ۱: توابع کمکی
        # =========================================================
        
        def get_database_context():
            products = ProductContent.objects.all()
            if not products: return "محصولی ثبت نشده."
            text = "لیست محصولات ما:\n"
            for p in products:
                text += f"- {p.product_name} | قیمت: {p.price} | موجودی: {p.inventory}\n"
            return text

        def ask_gemini_support(user_question):
            db_context = get_database_context()
            prompt = f"""
            تو پشتیبان فروشگاه هستی. بر اساس لیست محصولات زیر به مشتری جواب بده.
            محصولات: {db_context}
            سوال مشتری: {user_question}
            (اگر مشتری عکس خواست، بگو که کلمه 'عکس' را همراه نام محصول بفرستند)
            """
            try:
                return model.generate_content(prompt).text
            except:
                return "سیستم موقتاً در دسترس نیست."

        def generate_content_data(product_name):
            prompt = f"""
            محصول: "{product_name}"
            خروجی JSON:
            {{ "caption": "متن تبلیغاتی فارسی جذاب", "image_prompt": "English photorealistic description 8k" }}
            """
            try:
                response = model.generate_content(prompt)
                text = response.text.replace('```json', '').replace('```', '').strip()
                start, end = text.find('{'), text.rfind('}') + 1
                return json.loads(text[start:end]) if start != -1 else None
            except:
                return None

        # =========================================================
        # بخش ۲: هندلر تولید محتوا (با سیستم تلاش مجدد)
        # =========================================================
        
        @bot.message_handler(func=lambda m: m.text.startswith("تولید:"))
        def handle_content_generation(message):
            product_name = message.text.replace("تولید:", "").strip()
            chat_id = message.chat.id
            
            msg = bot.reply_to(message, f"⚙️ در حال ساخت محتوا برای: **{product_name}** ...")

            ai_data = generate_content_data(product_name)
            if not ai_data:
                bot.edit_message_text("❌ خطا در هوش مصنوعی.", chat_id, msg.message_id)
                return

            caption = ai_data['caption']
            img_prompt = ai_data['image_prompt']
            
            # [تغییر مهم] سیستم دانلود با تلاش مجدد (Retry Loop)
            img_url = f"https://image.pollinations.ai/prompt/{img_prompt.replace(' ', '%20')}?nologo=true&width=1024&height=1024&seed=42&model=flux"
            response = None
            
            bot.edit_message_text("🎨 در حال دانلود عکس (ممکن است کمی طول بکشد)...", chat_id, msg.message_id)

            for attempt in range(1, 4): # ۳ بار تلاش
                try:
                    print(f"⬇️ Attempt {attempt} to download image...")
                    response = requests.get(img_url, timeout=120) # تایم‌اوت ۱۲۰ ثانیه
                    if response.status_code == 200:
                        break # موفق شدیم، از حلقه خارج شو
                except Exception as e:
                    print(f"⚠️ Download failed (Attempt {attempt}): {e}")
                    time.sleep(2) # ۲ ثانیه صبر قبل از تلاش بعدی
            
            # بررسی نتیجه نهایی دانلود
            if response and response.status_code == 200:
                bot.delete_message(chat_id, msg.message_id)
                
                # ساخت محصول و ذخیره عکس
                product = ProductContent(
                    user_id=str(chat_id),
                    product_name=product_name,
                    generated_caption=caption,
                    image_prompt=img_prompt
                )
                
                file_name = f"{product_name.replace(' ', '_')}.jpg"
                product.product_image.save(file_name, ContentFile(response.content), save=True)
                
                markup = types.InlineKeyboardMarkup()
                btn_buy = types.InlineKeyboardButton("🛒 خرید سریع این محصول", callback_data=f"buy_id:{product.id}")
                markup.add(btn_buy)

                bot.send_photo(chat_id, response.content, caption=caption, reply_markup=markup)
                print(f"✅ Success: {product_name}")
            else:
                # [حالت اضطراری] اگر عکس دانلود نشد، حداقل متن را بفرستیم
                bot.delete_message(chat_id, msg.message_id)
                bot.send_message(chat_id, f"⚠️ عکس دانلود نشد (اینترنت ضعیف)، اما متن آماده شد:\n\n{caption}")
                
                # ذخیره محصول بدون عکس
                ProductContent.objects.create(
                    user_id=str(chat_id),
                    product_name=product_name,
                    generated_caption=caption,
                    image_prompt=img_prompt
                )

        # =========================================================
        # بخش ۳: سیستم خرید
        # =========================================================

        @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_id:'))
        def handle_buy_click(call):
            try:
                product_id = call.data.split(':')[1]
                product = ProductContent.objects.get(id=product_id)
                bot.answer_callback_query(call.id, f"انتخاب: {product.product_name}")
                msg = bot.send_message(call.message.chat.id, f"🛍 خرید **{product.product_name}**\n📞 شماره تماس:")
                bot.register_next_step_handler(msg, get_phone, product.product_name)
            except ProductContent.DoesNotExist:
                bot.send_message(call.message.chat.id, "❌ محصول یافت نشد.")

        def get_phone(message, product_name):
            phone = message.text
            msg = bot.reply_to(message, "📍 آدرس:")
            bot.register_next_step_handler(msg, get_address, product_name, phone)

        def get_address(message, product_name, phone):
            address = message.text
            user = message.chat.username or message.chat.first_name
            Order.objects.create(user_id=str(message.chat.id), username=user, product_name=product_name, phone_number=phone, address=address)
            bot.reply_to(message, "🎉 سفارش ثبت شد!")
            if ADMIN_ID.isdigit():
                try:
                    bot.send_message(ADMIN_ID, f"🔔 سفارش جدید!\n📦 {product_name}\n👤 {user}\n📞 {phone}")
                except: pass

        # =========================================================
        # بخش ۴: پشتیبانی + عکس
        # =========================================================

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            bot.reply_to(message, "سلام! 👋\n\n🔹 ادمین: **تولید: نام محصول**\n🔹 مشتری: سوال بپرسید یا بگویید **عکس [نام محصول]**")

        @bot.message_handler(content_types=['text'])
        def handle_support(message):
            text = message.text
            chat_id = message.chat.id

            if "عکس" in text or "تصویر" in text:
                products = ProductContent.objects.all()
                found_image = False
                for p in products:
                    if p.product_name in text and p.product_image:
                        bot.send_chat_action(chat_id, 'upload_photo')
                        try:
                            with open(p.product_image.path, 'rb') as photo:
                                bot.send_photo(chat_id, photo, caption=f"📸 {p.product_name}")
                            found_image = True
                            return
                        except Exception as e:
                            print(f"Error sending image: {e}")

                if not found_image:
                    bot.reply_to(message, "❌ عکس این محصول یافت نشد.")
                    return

            bot.send_chat_action(chat_id, 'typing')
            answer = ask_gemini_support(text)
            bot.reply_to(message, answer)

        bot.infinity_polling(timeout=20, long_polling_timeout=10)