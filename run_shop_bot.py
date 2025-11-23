from django.core.management.base import BaseCommand
from marketing_bot.models import ProductContent, Order
import telebot
from telebot import types
import google.generativeai as genai
import os

# تنظیمات اتصال مستقیم
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# --- تنظیمات ---
TELEGRAM_TOKEN = "8286709618:AAHBhc_TbGBDtOEGiw1exhxQD8HPn443Epc"
GOOGLE_API_KEY = "AIzaSyBuB8Erbmztj0IOhH_ursOcpqcXIete7nk"

# [مهم] آیدی عددی خودت (مدیر) را اینجا بنویس تا وقتی سفارش آمد خبرت کنم
# برای پیدا کردن آیدی خودت به ربات @userinfobot پیام بده
ADMIN_ID = "8400717984:AAHv2MSVB4veGcDfQu8g5qDrzhOQy5QUdRE"  # مثلا: "123456789"

class Command(BaseCommand):
    help = 'Runs the Complete Shop Bot (Support + Ordering)'

    def handle(self, *args, **kwargs):
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        self.stdout.write(self.style.SUCCESS('🛒 Shop Bot Started...'))

        # --- توابع کمکی هوش مصنوعی ---
        def get_database_context():
            products = ProductContent.objects.all()
            if not products: return "محصولی ثبت نشده."
            text = "محصولات ما:\n"
            for p in products:
                text += f"- {p.product_name} | قیمت: {p.price} | موجودی: {p.inventory}\n"
            return text

        def ask_gemini(question):
            db_context = get_database_context()
            prompt = f"""
            تو فروشنده باهوش هستی.
            اطلاعات محصولات:
            {db_context}
            
            سوال مشتری: {question}
            (اگر مشتری قصد خرید داشت، راهنمایی کن که کلمه 'سفارش' یا 'خرید' را ارسال کند)
            """
            try:
                return model.generate_content(prompt).text
            except:
                return "سیستم موقتا در دسترس نیست."

        # --- سیستم ثبت سفارش (Wizard) ---
        
        # گام ۱: شروع سفارش
        @bot.message_handler(func=lambda m: m.text in ['خرید', 'سفارش', 'ثبت سفارش'])
        def start_order_process(message):
            msg = bot.reply_to(message, "🛍 عالیه! چه محصولی رو میخوای سفارش بدی؟\n(نام محصول رو بنویس)")
            # اینجا میگیم: جواب بعدی کاربر رو ببر به تابع get_product_name
            bot.register_next_step_handler(msg, get_product_name)

        # گام ۲: دریافت نام محصول
        def get_product_name(message):
            product_name = message.text
            # حالا شماره تماس میخوایم. نام محصول رو پاس میدیم به تابع بعدی
            msg = bot.reply_to(message, f"✅ {product_name} انتخاب شد.\nحالا لطفاً شماره تماست رو بفرست:")
            bot.register_next_step_handler(msg, get_phone, product_name)

        # گام ۳: دریافت شماره تماس
        def get_phone(message, product_name):
            phone = message.text
            msg = bot.reply_to(message, "📍 لطفاً آدرس دقیق پستی رو بفرست:")
            bot.register_next_step_handler(msg, get_address, product_name, phone)

        # گام ۴: دریافت آدرس و ثبت نهایی
        def get_address(message, product_name, phone):
            address = message.text
            chat_id = message.chat.id
            username = message.chat.username or message.chat.first_name

            # ذخیره در دیتابیس
            Order.objects.create(
                user_id=str(chat_id),
                username=username,
                product_name=product_name,
                phone_number=phone,
                address=address
            )

            bot.send_message(chat_id, "🎉 سفارش شما با موفقیت ثبت شد!\nهمکاران ما به زودی با شما تماس می‌گیرند.")

            # خبر دادن به مدیر (شما)
            if ADMIN_ID != "YOUR_TELEGRAM_NUMERIC_ID":
                try:
                    admin_msg = f"""
                    🔔 **سفارش جدید!**
                    👤 خریدار: {username}
                    📦 محصول: {product_name}
                    📞 تلفن: {phone}
                    📍 آدرس: {address}
                    """
                    bot.send_message(ADMIN_ID, admin_msg)
                except:
                    print("خطا در ارسال پیام به مدیر (آیدی اشتباه است)")

        # --- هندلر عمومی (پاسخگویی هوشمند) ---
        # این باید آخر باشه که اگر پیام "خرید" نبود، بره سراغ هوش مصنوعی
        @bot.message_handler(func=lambda m: True)
        def handle_all_other_messages(message):
            # اگر کاربر وسط سفارش منصرف شد و چیز بی ربط گفت، اینجا هندل میشه
            bot.send_chat_action(message.chat.id, 'typing')
            response = ask_gemini(message.text)
            bot.reply_to(message, response)

        bot.infinity_polling()
#```

### راهنمای اجرا:

#۱. **پیدا کردن آیدی عددی خودتان:**
#   چون می‌خواهید وقتی مشتری سفارش داد، گوشی شما زنگ بخورد و بفهمید، باید `ADMIN_ID` را در خط ۲۱ کد بالا تنظیم کنید.
 #  * به ربات `@userinfobot` در تلگرام پیام دهید.
 #  * عددی که جلوی `Id` می‌نویسد (مثلاً `123456789`) را کپی کنید و جایگزین `YOUR_TELEGRAM_NUMERIC_ID` کنید.

#۲. **اجرا:**
#   ```bash
   