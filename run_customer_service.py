from django.core.management.base import BaseCommand
from marketing_bot.models import ProductContent
import telebot
import google.generativeai as genai
import os

# پاکسازی تنظیمات پروکسی
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# --- تنظیمات ---
TELEGRAM_TOKEN = "8286709618:AAHBhc_TbGBDtOEGiw1exhxQD8HPn443Epc"
GOOGLE_API_KEY = "AIzaSyBuB8Erbmztj0IOhH_ursOcpqcXIete7nk"

class Command(BaseCommand):
    help = 'Runs the Customer Service Bot (AI Support)'

    def handle(self, *args, **kwargs):
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        self.stdout.write(self.style.SUCCESS('🎧 Customer Service Bot Started... Ready to answer!'))

        # --- تابع ساخت پایگاه دانش (Knowledge Base) ---
        def get_database_context():
            """
            این تابع تمام محصولات را از دیتابیس می‌خواند و یک متن طولانی
            شامل اطلاعات همه آن‌ها می‌سازد تا به جمینی بدهیم.
            """
            products = ProductContent.objects.all()
            if not products:
                return "هنوز هیچ محصولی در فروشگاه ثبت نشده است."
            
            context_text = "لیست محصولات و مشخصات موجود در فروشگاه ما:\n"
            for p in products:
                context_text += f"""
                ---
                نام محصول: {p.product_name}
                قیمت: {p.price}
                رنگ‌های موجود: {p.colors}
                موجودی انبار: {p.inventory} عدد
                زمان ارسال: {p.delivery_time}
                توضیحات: {p.generated_caption[:100]}...
                """
            return context_text

        # --- تابع پاسخ‌دهی هوشمند ---
        def ask_gemini_support(user_question):
            # 1. دریافت اطلاعات روز از دیتابیس
            db_context = get_database_context()
            
            # 2. ساخت پرامپت حرفه‌ای برای پشتیبانی
            prompt = f"""
            نقش تو: یک پشتیبان فروشگاه اینترنتی بسیار مؤدب، صبور و حرفه‌ای هستی.
            وظیفه: پاسخ به سوال مشتری فقط و فقط بر اساس "اطلاعات محصولات" که در زیر آمده است.
            
            قوانین:
            1. اگر مشتری در مورد محصولی پرسید که در لیست زیر نیست، بگو "متاسفانه این محصول را موجود نداریم".
            2. قیمت‌ها را دقیق بگو.
            3. پاسخ‌های کوتاه و گرم بده (از ایموجی استفاده کن).
            4. اگر موجودی محصولی 0 بود، بگو "ناموجود".
            
            [اطلاعات محصولات / دیتابیس]:
            {db_context}
            
            ----------------
            سوال مشتری: {user_question}
            پاسخ تو:
            """
            
            try:
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"AI Error: {e}")
                return "متاسفانه در حال حاضر سیستم پاسخگویی قطع است."

        # --- هندلر پیام‌ها ---

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            bot.reply_to(message, "سلام! 🎧\nمن پشتیبان هوشمند هستم.\nهر سوالی درباره قیمت، موجودی یا مشخصات محصولات دارید بپرسید.")

        @bot.message_handler(content_types=['text'])
        def handle_customer_question(message):
            user_question = message.text
            chat_id = message.chat.id
            
            print(f"❓ Question: {user_question}")
            
            # نمایش وضعیت "در حال تایپ..."
            bot.send_chat_action(chat_id, 'typing')
            
            # دریافت جواب از هوش مصنوعی
            answer = ask_gemini_support(user_question)
            
            bot.reply_to(message, answer)

        # اجرای ربات
        bot.infinity_polling(timeout=20, long_polling_timeout=10)