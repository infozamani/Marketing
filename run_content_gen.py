from django.core.management.base import BaseCommand
from marketing_bot.models import ProductContent
from django.core.files.base import ContentFile  # [مهم] اضافه شده برای ذخیره فایل
import telebot
import google.generativeai as genai
import requests
import json
import os
import sys

# پاکسازی تنظیمات پروکسی
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# --- تنظیمات ---
TELEGRAM_TOKEN = "8286709618:AAHBhc_TbGBDtOEGiw1exhxQD8HPn443Epc"
GOOGLE_API_KEY = "AIzaSyBuB8Erbmztj0IOhH_ursOcpqcXIete7nk"

class Command(BaseCommand):
    help = 'Runs the Content Generator Bot (With Image Saving)'

    def handle(self, *args, **kwargs):
        print("🔄 Initializing Bot...", flush=True)
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        
        try:
            bot.remove_webhook()
        except Exception:
            pass

        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        print('🚀 Bot Started. Ready for requests!', flush=True)

        # --- توابع کمکی ---
        def generate_ai_content(product_name):
            prompt = f"""
            محصول: "{product_name}"
            خروجی JSON شامل:
            1. "caption": متن تبلیغاتی فارسی جذاب با ایموجی
            2. "image_prompt": توصیف انگلیسی دقیق برای عکس (Photorealistic, 8k)
            Output format: {{"caption": "...", "image_prompt": "..."}}
            """
            try:
                response = model.generate_content(prompt)
                cleaned_text = response.text.replace('```json', '').replace('```', '').strip()
                start = cleaned_text.find('{')
                end = cleaned_text.rfind('}') + 1
                if start != -1 and end != -1:
                    cleaned_text = cleaned_text[start:end]
                return json.loads(cleaned_text)
            except Exception as e:
                print(f"AI Error: {e}", flush=True)
                return None

        def generate_image_url(image_prompt):
            safe_prompt = image_prompt.replace(" ", "%20")
            return f"https://image.pollinations.ai/prompt/{safe_prompt}?nologo=true&width=1024&height=1024&seed=42&model=flux"

        # --- هندلرها ---

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            bot.reply_to(message, "سلام! 👋\nنام محصول را بفرستید تا محتوا بسازم و در دیتابیس ذخیره کنم.")

        @bot.message_handler(content_types=['text'])
        def handle_product_request(message):
            product_name = message.text
            chat_id = message.chat.id
            
            print(f"📝 Processing: {product_name}", flush=True)
            msg = bot.reply_to(message, f"⏳ در حال تولید محتوا برای: {product_name} ...")

            # 1. تولید متن
            ai_data = generate_ai_content(product_name)
            if not ai_data:
                bot.edit_message_text(text="❌ خطا در هوش مصنوعی.", chat_id=chat_id, message_id=msg.message_id)
                return
            
            caption = ai_data.get('caption')
            img_prompt = ai_data.get('image_prompt')

            bot.edit_message_text(text="🎨 در حال ساخت تصویر...", chat_id=chat_id, message_id=msg.message_id)

            # 2. تولید عکس و ذخیره‌سازی
            try:
                image_url = generate_image_url(img_prompt)
                response = requests.get(image_url, timeout=60)
                
                if response.status_code == 200:
                    bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                    
                    # ارسال به تلگرام
                    bot.send_photo(
                        chat_id=chat_id, 
                        photo=response.content, 
                        caption=caption
                    )
                    
                    # --- [تغییر اصلی اینجاست] ذخیره عکس در دیتابیس ---
                    # ابتدا شیء محصول را می‌سازیم (اما هنوز عکس ندارد)
                    product = ProductContent(
                        user_id=str(chat_id),
                        product_name=product_name,
                        generated_caption=caption,
                        image_prompt=img_prompt
                    )
                    
                    # ساخت نام فایل (مثلاً: kafsh_charm.jpg)
                    file_name = f"{product_name.replace(' ', '_')}.jpg"
                    
                    # ذخیره محتوای عکس (response.content) در فیلد عکس
                    product.product_image.save(file_name, ContentFile(response.content), save=True)
                    
                    print(f"✅ Finished & Saved Image: {product_name}", flush=True)
                else:
                    bot.send_message(chat_id, "❌ خطا در دانلود عکس.")

            except Exception as e:
                print(f"Error: {e}", flush=True)
                bot.send_message(chat_id, "خطا در ارتباط.")

        bot.infinity_polling(timeout=20, long_polling_timeout=10)