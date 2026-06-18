import logging
import asyncio
import random
import time
import os
import json
import unicodedata
import re
import io
import difflib
import requests
import httpx  
import aiohttp
import arabic_reshaper
import math
import traceback
import numpy as np
import pandas as pd
from aiohttp import web
from scipy.stats import linregress
from scipy.signal import find_peaks
from typing import Dict, Union
from aiogram import types
from datetime import datetime, timedelta # 💡 تمت الإضافة هنا
from aiogram.dispatcher.filters import Text 
from pilmoji import Pilmoji 
from PIL import Image, ImageDraw, ImageFont, ImageOps
from bidi.algorithm import get_display
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# --- [ 1. إعدادات الهوية والاتصال ] ---
ADMIN_ID = 8806781380
OWNER_USERNAME = ""

# سحب التوكينات من Render (لن يعمل البوت بدونها في الإعدادات)
API_TOKEN = os.getenv('BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
GROUP_ID = os.getenv('GROUP_ID')
# قناة تقارير الذكاء الاصطناعي (يجب إضافتها في متغيرات Render)
AI_CHANNEL_ID = os.getenv('AI_CHANNEL_ID')
# ==========================================
# 🌟 جلب مفاتيح الذكاء الاصطناعي بأمان من البيئة
# ==========================================
AI_HEARTS = [
    {"name": "القلب 1 (Gemini الأساسي)", "type": "gemini", "key": os.getenv("GEMINI_API_KEY_1")},
    {"name": "القلب 2 (Gemini احتياطي 1)", "type": "gemini", "key": os.getenv("GEMINI_API_KEY_2")},
    {"name": "القلب 3 (Gemini احتياطي 2)", "type": "gemini", "key": os.getenv("GEMINI_API_KEY_3")},
    {"name": "القلب 4 (Groq طوارئ 1)", "type": "groq", "key": os.getenv("GROQ_API_KEY_1")},
    {"name": "القلب 5 (Groq طوارئ 2)", "type": "groq", "key": os.getenv("GROQ_API_KEY_2")}
]

# التحقق ثانياً
# 2. التحقق ثانياً
if not API_TOKEN or not GROUP_ID or not AI_CHANNEL_ID:
    logging.error("❌ خطأ: المتغيرات المشفرة مفقودة في إعدادات Render!")

# تعريف المحركات
bot = Bot(token=API_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 1. في بداية الملف (خارج كل الدوال) قم بتعريف هذا المتغير
bot_username = None

# ==========================================
# 1. إعدادات الجلسات والقيم الثابتة (Config & State)
# ==========================================
# --- منطقة تعريف المتغيرات العالمية (Global Variables) ---
active_investigations = {}
# 1. تخزين بيانات جلسات التداول المؤقتة لكل مستخدم
trade_sessions = {} 

# 2. إدارة مهام التحديث اللحظي (Tasks) لمنع التكرار والحظر
# يجب أن يكون قاموساً (Dictionary) لكي نتمكن من إلغاء المهمة السابقة لكل مستخدم
active_updates = {} 


async def fetch_supabase(endpoint):
    """دالة لجلب البيانات من Supabase مباشرة"""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            return await response.json()
            
async def ask_gemini(prompt):
    """
    القلب الهجين: يبدأ بعبقرية جمناي لاستخراج أدق التفاصيل، 
    وإذا تعطلت كل خوادم جوجل، ينقض بـ Groq كخطة إنقاذ أخيرة.
    """
    async with aiohttp.ClientSession() as session:
        # حلقة المرور على الترسانة بالترتيب
        for heart in AI_HEARTS:
            heart_name = heart["name"]
            provider = heart["type"]
            key = heart["key"]
            
            # تجهيز حمولة الطلب بناءً على نوع العقل
            if provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                headers = {"Content-Type": "application/json"}
            else: # قوة طوارئ Groq
                url = "https://api.groq.com/openai/v1/chat/completions"
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                }

            try:
                async with session.post(url, json=payload, headers=headers) as response:
                    data = await response.json()
                    
                    if response.status == 200:
                        # استخراج النص بذكاء بناءً على المزود
                        if provider == "gemini":
                            text = data['candidates'][0]['content']['parts'][0]['text']
                        else:
                            text = data['choices'][0]['message']['content']
                            
                        print(f"✅ تمت العملية بنجاح باستخدام: {heart_name}")
                        return re.sub(r'<[^>]+>', '', text) # تنظيف HTML لتيليجرام
                    
                    else:
                        print(f"⚠️ {heart_name} الخادم رد بالكود ({response.status})، يتم تحويل مسار الطاقة...")
                        
            except Exception as e:
                print(f"❌ تعطل في {heart_name}: {str(e)}، يتم التحويل للمحرك التالي...")
                
    return "⚠️ عذراً أيها القائد، جميع الأنظمة والترسانة الاحتياطية تحت ضغط عالمي هائل الآن."

async def analyze_trend_structure_with_ai(report_id: str, symbol: str):
    """
    🧠 خوارزمية الاستلام الفني: تقوم بفتح ملف القضية (report_id)، 
    قراءة جميع الأدلة الرقمية (المتوسطات، إيشيموكو، سوبر تريند، كيلتنر، إلخ)،
    وتحديث هيكل الاتجاه في قاعدة البيانات وإرساله للقناة المخصصة.
    """
    print(f"🕵️‍♂️ [المختبر الجنائي] جاري سحب بيانات {symbol} للتحليل الاصطناعي العميق...")
    
    try:
        # 1. جلب بيانات جميع المؤشرات من مسرح الجريمة (Supabase)
        endpoint = f"moving_averages_and_bands?select=*&report_id=eq.{report_id}"
        records = await fetch_supabase(endpoint) # نفترض أن هذه الدالة موجودة لديك
        
        if not records or (isinstance(records, dict) and "error" in records):
            print(f"❌ [المختبر الجنائي] الملف {report_id} غير موجود أو فارغ!")
            return

        evidence = records[0]

        # 2. هندسة البرومبت الصارم للذكاء الاصطناعي (ترتيب المؤشرات فقط بدون السعر)
        prompt = f"""
        أنت مجرد "أداة استخراج برمجية" (Data Extractor).
        يُمنع منعاً باتاً الشرح، التأليف، أو إضافة أي نصوص وصفية، مقدمات أو خاتمات.

        بيانات السجل:
        {json.dumps(evidence, default=str)}

        المطلوب منك:
        1. استخراج قيم جميع المؤشرات وترتيبها هرمياً باستخدام الشروط الرياضية (>, <, =).
        2. يُمنع منعاً باتاً تضمين "السعر" (Price) أو ذكره في الترتيب. رتب المؤشرات مع بعضها البعض فقط بناءً على قيمها.
        3. اجمع جميع المؤشرات في أسطر رياضية واضحة لكل فريم زمني من الأكبر قيمة إلى الأصغر قيمة. (مثال: EMA20 > SuperTrend > EMA50 > Parabolic_SAR > EMA100 > EMA200). 
        4. إذا كانت بيانات الفريم فارغة لا تذكرها .

        ⚠️ قواعد صارمة جداً:
        1. يجب أن يكون ردك بصيغة JSON حقيقية وصالحة للبرمجة فقط.
        2. يُمنع منعاً باتاً إضافة أي نصوص أو علامات Markdown خارج الـ JSON.
        3. ترتيب البيانات حرفياً موقع كل مؤشر :
        {{
            "trend_structure_1h": "...",
            "trend_structure_2h": "...",
            "trend_structure_4h": "...",
            "trend_structure_1d": "..."
        }}
        """

        # 3. إرسال البيانات للعقل المدبر (Gemini)
        ai_response = await ask_gemini(prompt) # نفترض أن هذه الدالة موجودة لديك
        
        # 4. تنظيف النص لتفادي أخطاء Termux
        clean_json_str = ai_response.replace("```json", "").replace("```", "").strip()
        
        try:
            analysis_data = json.loads(clean_json_str)
        except json.JSONDecodeError:
            print(f"❌ [المختبر الجنائي] فشل قراءة رد الذكاء الاصطناعي كـ JSON لعملة {symbol}. الرد كان:\n{clean_json_str}")
            return

        # 5. تجهيز حمولة التحديث (Payload)
        update_payload = {
            "trend_structure_1h": analysis_data.get("trend_structure_1h", "Null"),
            "trend_structure_2h": analysis_data.get("trend_structure_2h", "Null"),
            "trend_structure_4h": analysis_data.get("trend_structure_4h", "Null"),
            "trend_structure_1d": analysis_data.get("trend_structure_1d", "Null")
        }

        # 6. حقن البيانات الجديدة (PATCH) في قاعدة سوبابيس
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        url = f"{SUPABASE_URL}/rest/v1/moving_averages_and_bands?report_id=eq.{report_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=update_payload, headers=headers) as resp:
                if resp.status in [200, 204]:
                    print(f"✅ [المختبر الجنائي] تم تفكيك شفرة هيكل الاتجاه بنجاح للعملة: {symbol}")
                    
                    # --- [ 7. إرسال التقرير إلى قناة تلجرام الخاصة بالذكاء الاصطناعي ] ---
                    telegram_report = (
                        f"🕵️‍♂️ <b>التقرير التحليل الفني | #{symbol}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n\n"
                        f"⏱ <b>[ 1H ]:</b>\n"
                        f"{update_payload['trend_structure_1h']}\n\n"
                        f"⏱ <b>[ 2H ]:</b>\n"
                        f"{update_payload['trend_structure_2h']}\n\n"
                        f"⏱ <b>[ 4H ]:</b>\n"
                        f"{update_payload['trend_structure_4h']}\n\n"
                        f"📅 <b>[ 1D ]:</b>\n"
                        f"{update_payload['trend_structure_1d']}\n\n"
                        f"🔗 <b>معرف القضية:</b> <code>{report_id}</code>"
                    )
                    
                    try:
                        await bot.send_message(chat_id=AI_CHANNEL_ID, text=telegram_report)
                        print(f"📨 [تلجرام] تم إرسال ملف القضية لعملة {symbol} إلى القناة بنجاح.")
                    except Exception as tg_err:
                        print(f"⚠️ [تلجرام] فشل إرسال التقرير للقناة: {tg_err}")

                else:
                    error_text = await resp.text()
                    print(f"⚠️ [المختبر الجنائي] فشل تحديث سوبابيس: الكود {resp.status} - {error_text}")

    except Exception as e:
        print(f"❌ [المختبر الجنائي] انهيار في غرفة التحليل لعملة {symbol}: {str(e)}")
        

# ==========================================
class BankTransfer(StatesGroup):
    waiting_for_amount = State()      # انتظار مبلغ التحويل/الإيداع
    waiting_for_account = State()     # انتظار رقم الحساب (في حال التحويل لشخص)

# ==========================================
# 6. معالج أمر البدء المطور في الخاص /start
# ==========================================
@dp.message_handler(commands=['start'], chat_type=types.ChatType.PRIVATE)
async def private_start_handler(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "بدون معرف"
    full_name = f"{first_name} {last_name}".strip()
    
    # ---------------------------------------------------------
    # 🚨 [ نظام إنذار المطور: إرسال إشعار للمجموعة بدخول شخص جديد ]
    # ---------------------------------------------------------
    try:
        # تأكد أن المتغير GROUP_ID مسحوب بشكل صحيح في بداية ملفك
        if GROUP_ID: 
            # إنشاء رابط يفتح بروفايل الشخص بمجرد الضغط على اسمه
            user_profile_link = f"<a href='tg://user?id={user_id}'>{full_name}</a>"
            
            alert_msg = (
                f"🚨 <b>رادار البوت: مستخدم جديد!</b>\n\n"
                f"👤 <b>الاسم:</b> {user_profile_link}\n"
                f"🔗 <b>المعرف:</b> {username}\n"
                f"🆔 <b>الآيدي:</b> <code>{user_id}</code>"
            )
            # إرسال الإشعار للمجموعة
            await bot.send_message(chat_id=GROUP_ID, text=alert_msg, parse_mode="HTML")
    except Exception as e:
        import logging
        logging.error(f"❌ خطأ في إرسال إشعار دخول المستخدم للمجموعة: {e}")

    # ---------------------------------------------------------
    # 📲 [ لوحة الأزرار ورسالة الترحيب للمستخدم ]
    # ---------------------------------------------------------
    kb_start = InlineKeyboardMarkup(row_width=2)
    kb_start.add(
        InlineKeyboardButton("💻 تواصل مع المطور", url="https://t.me/Ya_79k"),
        InlineKeyboardButton("📢 قناة البوت", url="https://t.me/YourChannel") # لا تنسَ تعديل رابط القناة هنا
    )

    # تحسين التنسيق ليكون أكثر احترافية وفخامة
    welcome_msg = (
        f"👋 <b>أهلاً بك يا {first_name} في أعظم نظام تداول في سوق العملات الرقمية!</b> 🚀\n\n"
        f"يتفوق هذا النظام على البنوك، صناديق التحوط، والمواقع المدفوعة بمراحل؛ بل هي مجرد ألعاب أطفال مقارنةً بالمنطق الجبار الذي يحتويه.\n\n"
        f"👁️‍🗨️ <b>ماذا يقدم لك النظام؟</b>\n"
        f"• كاشف متقدم للسوق، الخديعة، المصائد، وتلاعبات الحيتان.\n"
        f"• أسرار وخفايا حصرية لا تُدرّس حتى في الجامعات.\n"
        f"• نظام إنذار استباقي قبل وقوع الأحداث بمليون مرة .\n"
        f"• نظام إجراء صفقات آلي كل ما عليك هو ربط حسابك بالنظام وهو يقوم بالتداول بدلاً عنك واكثر أمانا بنسبة 100.\n"
        f"• درع أمان متكامل لحمايتك من فوضى وتقلبات السوق ضمان لو خسرت تتعوض والخسارة عندنا مستحيلة.\n\n"
        f"💳 <b> تفاصيل أسعار الباقات بالدولار:</b>\n"
        f"▫️ أسبوع: <b>25$</b>\n"
        f"▫️ شهر: <b>100$</b>\n"
        f"▫️ 3 أشهر: <b>250$</b>\n"
        f"▫️ 6 أشهر: <b>400$</b>\n"
        f"▫️ سنة كاملة: <b>600$</b>\n\n"
        f"<i>🤍 ملاحظة: جميع أموال الاشتراكات تذهب لدعم الفقراء واليتامى ابتغاء وجه الله تعالى اما انا مكتفي بما علمني ربي واعطاني من فضله.</i>\n\n"
        f"💬 <b>للتواصل المباشر مع المطور، طلب الاشتراك، أو الإبلاغ عن خلل فني، يرجى استخدام الأزرار أدناه.</b>\n"
        f"نتمنى لكم التوفيق والنجاح الدائم اكتشف اسرار مخفية عنك وكن مليونير."
    )
    
    try:
        # Photo ID الخاص بصورة الترحيب (يفضل صورة فخمة للبوت)
        bot_photo = "AgACAgQAAxkBAA..." 
        await message.answer_photo(
            photo=bot_photo,
            caption=welcome_msg,
            reply_markup=kb_start,
            parse_mode="HTML"
        )
    except Exception:
        # في حال كانت الصورة غير صالحة، يرسل النص فقط
        await message.answer(welcome_msg, reply_markup=kb_start, parse_mode="HTML")

# ==========================================
# --- [ دوال الحساب الرياضي ] ---
# ==========================================
def calculate_ema(data, period):
    if len(data) < period: return data[-1]
    alpha = 2 / (period + 1)
    ema = sum(data[:period]) / period
    for price in data[period:]:
        ema = (price * alpha) + (ema * (1 - alpha))
    return ema
    
def calculate_rsi(series, period: int = 14):
    if isinstance(series, list):
        series = pd.Series(series)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    # نرجع آخر قيمة كرقم صافي بدلاً من Series كاملة
    return float(rsi.values[-1]) if len(rsi) > 0 and not pd.isna(rsi.values[-1]) else 50.0
    

def calculate_bollinger(data, period=20):
    if len(data) < period: return data[-1], data[-1], data[-1]
    recent = data[-period:]
    sma = sum(recent) / period
    variance = sum((x - sma) ** 2 for x in recent) / period
    std_dev = math.sqrt(variance)
    return sma + (std_dev * 2), sma, sma - (std_dev * 2)


def calculate_volume(volumes):
    """
    تعيد حجم التداول للشمعة الحالية (العمود الأخير)
    هذا هو المحرك الذي يكشف دخول السيولة المفاجئ.
    """
    if not volumes: return 0.0
    
    # جلب حجم تداول الشمعة الأخيرة (آخر عمود في الشارت)
    current_volume = float(volumes[-1])
    
    return current_volume
    
def calculate_obv(closes, volumes):
    """
    حساب مؤشر حجم التداول المتوازن (OBV)
    يعتمد على العلاقة بين سعر الإغلاق وحجم التداول
    """
    if len(closes) < 2: return 0.0
    
    obv = 0.0
    # نبدأ الحساب بمقارنة كل شمعة بالتي قبلها
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            # إغلاق صاعد: أضف الفوليوم
            obv += volumes[i]
        elif closes[i] < closes[i-1]:
            # إغلاق هابط: اطرح الفوليوم
            obv -= volumes[i]
        # إذا تساوى الإغلاق يبقى الـ OBV كما هو دون تغيير
            
    return obv

def calculate_bbw(upper, lower, middle):
    """
    تحسب عرض نطاق البولنجر (BBW).
    المعادلة: (الخط العلوي - الخط السفلي) / الخط الأوسط
    """
    try:
        if middle > 0:
            return (upper - lower) / middle
        return 0
    except Exception:
        return 0
  

def calculate_keltner_channels(highs, lows, closes, ema_period=20, atr_period=10, multiplier=2):
    if len(closes) < max(ema_period, atr_period) + 1:
        return closes[-1], closes[-1], closes[-1]
    mid = calculate_ema(closes, ema_period)
    atr_v = calculate_atr(highs, lows, closes, atr_period)
    return mid + (multiplier * atr_v), mid, mid - (multiplier * atr_v)
    
# ==========================================
# --- [ دوال الأدوات المحرمة - قلعة أثر ] ---
# ==========================================

def calculate_atr(highs, lows, closes, period=14):
    """
    نسخة قلعة أثر المعتمدة (Wilder's ATR)
    أدق في حساب الستوب لوز ومنع ضربه بالذيول العشوائية.
    """
    if len(closes) < period + 1: return 0.0
    
    tr_list = []
    for i in range(1, len(closes)):
        # حساب المدى الحقيقي (True Range)
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    
    # حساب أول قيمة كمتوسط بسيط (SMA) لتبدأ منه
    atr = sum(tr_list[:period]) / period
    
    # تطبيق التنعيم (Smoothing) لبقية القيم - هذا هو "سر" الاستقرار
    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        
    return round(atr, 6)

def calculate_adx(highs, lows, closes, period=14):
    """
    قاعدة (المرصاد): حساب مؤشر ADX
    لمعرفة هل العملة في "انفجار" (ADX > 25) أم "تذبذب" (ADX < 20).
    """
    if len(closes) < period * 2: return 0.0
    
    plus_dm = []
    minus_dm = []
    tr_list = []
    
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        
        plus_dm.append(max(up_move, 0) if up_move > down_move else 0)
        minus_dm.append(max(down_move, 0) if down_move > up_move else 0)
        
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)

    # حساب الـ DI والـ DX (تبسيطاً للمحرك اليدوي)
    # ملاحظة: هذه نسخة مختصرة لتناسب الأداء السريع في البوت
    avg_tr = sum(tr_list[-period:]) / period
    avg_plus_dm = sum(plus_dm[-period:]) / period
    avg_minus_dm = sum(minus_dm[-period:]) / period
    
    plus_di = 100 * (avg_plus_dm / avg_tr) if avg_tr != 0 else 0
    minus_di = 100 * (avg_minus_dm / avg_tr) if avg_tr != 0 else 0
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) != 0 else 0
    return round(dx, 2)

def calculate_volume_delta(buy_volumes, total_volumes):
    """
    قاعدة (فَتَبَيَّنُوا): حساب صافي السيولة (Volume Delta)
    يميز بين "الزبد" (فوليوم وهمي) و"ما ينفع الناس" (شراء حقيقي).
    """
    if not buy_volumes or not total_volumes: return 0.0
    
    # صافي السيولة = حجم الشراء - حجم البيع (البيع هو الإجمالي ناقص الشراء)
    current_buy = float(buy_volumes[-1])
    current_total = float(total_volumes[-1])
    current_sell = current_total - current_buy
    
    delta = current_buy - current_sell
    return round(delta, 2)

def get_market_mood(rsi_value):
    """
    سيكولوجية (هَلُوعًا ومَنُوعًا): بناءً على مستويات أثر 78/22
    """
    if rsi_value >= 78: return "GREED (MANOU'A)"
    if rsi_value <= 22: return "FEAR (HALOU'A)"
    if rsi_value >= 50: return "BULLISH_BIAS"
    return "BEARISH_BIAS"
    
    
# ==========================================
# 1. دالة تحليل أنماط الشموع اليابانية
# ==========================================
import numpy as np

def detect_all_pdf_patterns(df):
    if len(df) < 5:
        return "Not enough data"

    # تحويل البيانات لمصفوفات Numpy للسرعة
    op = df['open'].values
    hi = df['high'].values
    lo = df['low'].values
    cl = df['close'].values
    
    # حسابات أساسية
    body = np.abs(cl - op)
    upper_wick = hi - np.maximum(op, cl)
    lower_wick = np.minimum(op, cl) - lo
    candle_range = hi - lo
    
    # تجنب القسمة على صفر
    candle_range = np.where(candle_range == 0, 0.00001, candle_range)
    direction = np.where(cl > op, 1, -1)
    # استبدل السطر القديم بهذا:
    window = min(20, len(body)) # يأخذ 20 أو أقل إذا كانت الشموع قليلة
    avg_body = np.convolve(body, np.ones(window)/window, mode='same')
    
    # نسبة التسامح للقمم والقيعان المتساوية
    tolerance = avg_body * 0.1 

    # المؤشرات المكانية (لآخر 5 شموع لتحديد النماذج المعقدة)
    curr, prev, pprev, p3, p4 = -1, -2, -3, -4, -5

    # --- 1. الشروط الأساسية للفحص السريع ---
    is_doji = body <= (candle_range * 0.1)
    is_marubozu = body >= (candle_range * 0.95)
    is_dragon_doji = is_doji & (lower_wick >= body * 3) & (upper_wick <= candle_range * 0.1)
    is_gravestone_doji = is_doji & (upper_wick >= body * 3) & (lower_wick <= candle_range * 0.1)
    is_hammer_type = (lower_wick >= body * 2) & (upper_wick <= candle_range * 0.1) & (body > candle_range * 0.1)
    is_star_type = (upper_wick >= body * 2) & (lower_wick <= candle_range * 0.1) & (body > candle_range * 0.1)
    is_spinning_top = (body < avg_body * 0.8) & (upper_wick > body) & (lower_wick > body)
    is_long_body = body > avg_body * 1.5

    # الفجوات السعرية (Gaps)
    gap_up = lo[curr] > hi[prev]
    gap_down = hi[curr] < lo[prev]

    # حساب الاتجاه البسيط (مقارنة الإغلاق السابق بـ 4 شموع قبلها) - يُستخدم للأنماط الفردية
    prev_trend = 1 if cl[prev] > cl[p4] else -1 

    res = "Normal"
    
    # ==========================================
    # --- 2. الأنماط الخماسية والرباعية (5 & 4 Candles) ---
    # ==========================================

    # Rising Three Methods (صاعد)
    if direction[p4] == 1 and is_long_body[p4] and \
       direction[p3] == -1 and direction[pprev] == -1 and direction[prev] == -1 and \
       direction[curr] == 1 and cl[curr] > hi[p4] and \
       max(hi[p3], hi[pprev], hi[prev]) < hi[p4] and min(lo[p3], lo[pprev], lo[prev]) > lo[p4]:
        res = "طرق_الارتفاع_الثلاثة_صاعد"

    # Falling Three Methods (هابط)
    elif direction[p4] == -1 and is_long_body[p4] and \
         direction[p3] == 1 and direction[pprev] == 1 and direction[prev] == 1 and \
         direction[curr] == -1 and cl[curr] < lo[p4] and \
         max(hi[p3], hi[pprev], hi[prev]) < hi[p4] and min(lo[p3], lo[pprev], lo[prev]) > lo[p4]:
        res = "طرق_الانخفاض_الثلاثة_هابط"

    # Concealing Baby Swallow (ابتلاع الطفل الرضيع - هابط يتحول لصاعد)
    elif direction[p3] == -1 and is_marubozu[p3] and direction[pprev] == -1 and is_marubozu[pprev] and \
         direction[prev] == -1 and is_star_type[prev] and gap_down and \
         direction[curr] == -1 and cl[curr] > cl[prev] and op[curr] > hi[prev]:
        res = "ابتلاع_الطفل_الرضيع_صاعد"

    # Mat Hold (القبضة المحكمة - صاعد)
    elif direction[p4] == 1 and is_long_body[p4] and \
         direction[p3] == -1 and lo[p3] > hi[p4] and \
         direction[pprev] == -1 and direction[prev] == -1 and \
         min(lo[p3], lo[pprev], lo[prev]) > lo[p4] and \
         direction[curr] == 1 and cl[curr] > hi[p3]:
        res = "القبضة_المحكمة_صاعد"

    # ==========================================
    # --- 3. الأنماط الثلاثية (3 Candles) ---
    # ==========================================

    # Abandoned Baby (الطفل المهجور)
    elif direction[pprev] == -1 and is_doji[prev] and lo[pprev] > hi[prev] and direction[curr] == 1 and lo[curr] > hi[prev]:
        res = "الطفل_المهجور_صاعد"
    elif direction[pprev] == 1 and is_doji[prev] and hi[pprev] < lo[prev] and direction[curr] == -1 and hi[curr] < lo[prev]:
        res = "الطفل_المهجور_هابط"

    # Morning / Evening Stars
    elif direction[pprev] == -1 and direction[curr] == 1 and cl[curr] > (op[pprev] + cl[pprev])/2 and op[prev] < cl[pprev] and cl[prev] < op[curr]:
        res = "نجمة_الصباح_دوجي_صاعد" if is_doji[prev] else "نجمة_الصباح_صاعد"
    elif direction[pprev] == 1 and direction[curr] == -1 and cl[curr] < (op[pprev] + cl[pprev])/2 and op[prev] > cl[pprev] and cl[prev] > op[curr]:
        res = "نجمة_المساء_دوجي_هابط" if is_doji[prev] else "نجمة_المساء_هابط"

    # Three White Soldiers / Three Black Crows
    elif direction[pprev] == 1 and direction[prev] == 1 and direction[curr] == 1 and cl[curr] > cl[prev] > cl[pprev] and op[curr] > op[prev] > op[pprev]:
        res = "الجنود_الثلاثة_البيض_صاعد"
    elif direction[pprev] == -1 and direction[prev] == -1 and direction[curr] == -1 and cl[curr] < cl[prev] < cl[pprev] and op[curr] < op[prev] < op[pprev]:
        res = "الغربان_الثلاثة_السود_هابط"

    # Three Inside Up / Down
    elif direction[pprev] == -1 and direction[prev] == 1 and op[prev] > cl[pprev] and cl[prev] < op[pprev] and direction[curr] == 1 and cl[curr] > cl[prev]:
        res = "ثلاثة_للداخل_صاعد"
    elif direction[pprev] == 1 and direction[prev] == -1 and op[prev] < cl[pprev] and cl[prev] > op[pprev] and direction[curr] == -1 and cl[curr] < cl[prev]:
        res = "ثلاثة_للداخل_هابط"

    # Three Outside Up / Down
    elif direction[pprev] == -1 and direction[prev] == 1 and op[prev] < cl[pprev] and cl[prev] > op[pprev] and direction[curr] == 1 and cl[curr] > cl[prev]:
        res = "ثلاثة_للخارج_صاعد"
    elif direction[pprev] == 1 and direction[prev] == -1 and op[prev] > cl[pprev] and cl[prev] < op[pprev] and direction[curr] == -1 and cl[curr] < cl[prev]:
        res = "ثلاثة_للخارج_هابط"

    # Upside / Downside Tasuki Gap
    elif direction[pprev] == 1 and direction[prev] == 1 and lo[prev] > hi[pprev] and direction[curr] == -1 and op[curr] < cl[prev] and cl[curr] < op[prev] and cl[curr] > hi[pprev]:
        res = "فجوة_تاسوكي_صاعدة"
    elif direction[pprev] == -1 and direction[prev] == -1 and hi[prev] < lo[pprev] and direction[curr] == 1 and op[curr] > cl[prev] and cl[curr] > op[prev] and cl[curr] < lo[pprev]:
        res = "فجوة_تاسوكي_هابطة"

    # Tri-Star (النجوم الثلاثة)
    elif is_doji[pprev] and is_doji[prev] and is_doji[curr]:
        res = "صاعد_النجوم_الثلاثة_تغير اتجاه صعود او هبوط "

    # Advance Block (التقدم المعاق - هابط)
    elif direction[pprev] == 1 and direction[prev] == 1 and direction[curr] == 1 and \
         op[prev] > op[pprev] and op[prev] < cl[pprev] and \
         op[curr] > op[prev] and op[curr] < cl[prev] and \
         body[curr] < body[prev] < body[pprev] and \
         upper_wick[curr] > upper_wick[prev]:
        res = "التقدم_المعاق_هابط"

    # Stalled Pattern / Deliberation (نموذج التروي - هابط)
    elif direction[pprev] == 1 and is_long_body[pprev] and \
         direction[prev] == 1 and is_long_body[prev] and \
         direction[curr] == 1 and body[curr] < (avg_body[curr] * 0.5) and \
         op[curr] >= (cl[prev] - tolerance[curr]):
        res = "نموذج_التروي_هابط"

    # Upside Gap Two Crows (غرابان بفجوة صاعدة - هابط)
    elif direction[pprev] == 1 and is_long_body[pprev] and \
         direction[prev] == -1 and lo[prev] > hi[pprev] and \
         direction[curr] == -1 and op[curr] > op[prev] and cl[curr] < cl[prev] and cl[curr] > op[pprev]:
        res = "غرابان_بفجوة_صاعدة_هابط"

    # Unique Three River Bottom (نهر الثلاثة الفريد - صاعد)
    elif direction[pprev] == -1 and is_long_body[pprev] and \
         direction[prev] == -1 and lower_wick[prev] >= (body[prev] * 2) and cl[prev] > lo[pprev] and \
         direction[curr] == 1 and body[curr] < avg_body[curr] and cl[curr] < cl[prev]:
        res = "نهر_الثلاثة_الفريد_صاعد"

    # Stick Sandwich (الساندوتش - صاعد)
    elif direction[pprev] == -1 and direction[prev] == 1 and direction[curr] == -1 and \
         op[curr] > cl[prev] and cl[curr] < op[prev] and \
         abs(cl[curr] - cl[pprev]) <= tolerance[curr]:
        res = "الساندوتش_صاعد"

    # ==========================================
    # --- 4. الأنماط الثنائية (2 Candles) ---
    # ==========================================

    # Engulfing (الابتلاع)
    elif direction[prev] == -1 and direction[curr] == 1 and op[curr] <= cl[prev] and cl[curr] >= op[prev]:
        res = "ابتلاع_صاعد"
    elif direction[prev] == 1 and direction[curr] == -1 and op[curr] >= cl[prev] and cl[curr] <= op[prev]:
        res = "ابتلاع_هابط"

    # Harami & Harami Cross (الهارامي والهارامي الصليب)
    elif direction[prev] == -1 and direction[curr] == 1 and op[curr] > cl[prev] and cl[curr] < op[prev]:
        res = "هارامي_صليب_صاعد" if is_doji[curr] else "هارامي_صاعد"
    elif direction[prev] == 1 and direction[curr] == -1 and op[curr] < cl[prev] and cl[curr] > op[prev]:
        res = "هارامي_صليب_هابط" if is_doji[curr] else "هارامي_هابط"

    # Piercing Line & Dark Cloud Cover
    elif direction[prev] == -1 and direction[curr] == 1 and op[curr] < cl[prev] and cl[curr] > (op[prev] + cl[prev])/2 and cl[curr] < op[prev]:
        res = "الخط_الثاقب_صاعد"
    elif direction[prev] == 1 and direction[curr] == -1 and op[curr] > cl[prev] and cl[curr] < (op[prev] + cl[prev])/2 and cl[curr] > op[prev]:
        res = "السحابة_القاتمة_هابط"

    # Kicker
    elif direction[prev] == -1 and direction[curr] == 1 and op[curr] >= op[prev] and lo[curr] > hi[prev]:
        res = "الراكل_صاعد"
    elif direction[prev] == 1 and direction[curr] == -1 and op[curr] <= op[prev] and hi[curr] < lo[prev]:
        res = "الراكل_هابط"

    # Meeting Lines (خطوط التلاقي)
    elif direction[prev] == -1 and direction[curr] == 1 and abs(cl[curr] - cl[prev]) <= tolerance[curr]:
        res = "خطوط_التلاقي_صاعد"
    elif direction[prev] == 1 and direction[curr] == -1 and abs(cl[curr] - cl[prev]) <= tolerance[curr]:
        res = "خطوط_التلاقي_هابط"

    # Separating Lines (خطوط الانفصال)
    elif direction[prev] == -1 and direction[curr] == 1 and abs(op[curr] - op[prev]) <= tolerance[curr]:
        res = "خطوط_الانفصال_صاعد"
    elif direction[prev] == 1 and direction[curr] == -1 and abs(op[curr] - op[prev]) <= tolerance[curr]:
        res = "خطوط_الانفصال_هابط"

    # Matching Low (القيعان المتطابقة)
    elif direction[prev] == -1 and direction[curr] == -1 and abs(cl[curr] - cl[prev]) <= tolerance[curr]:
        res = "القيعان_المتطابقة_صاعد"

    # Homing Pigeon (الحمامة الزاجلة)
    elif direction[prev] == -1 and direction[curr] == -1 and op[curr] < op[prev] and cl[curr] > cl[prev]:
        res = "الحمامة_الزاجلة_صاعد"

    # On Neck / In Neck
    elif direction[prev] == -1 and direction[curr] == 1 and abs(cl[curr] - lo[prev]) <= tolerance[curr]:
        res = "على_الرقبة_هابط"
    elif direction[prev] == -1 and direction[curr] == 1 and cl[curr] > cl[prev] and cl[curr] < (op[prev] + cl[prev])/2:
        res = "في_الرقبة_هابط"

    # Tweezer Top / Bottom
    elif direction[prev] == 1 and direction[curr] == -1 and abs(hi[curr] - hi[prev]) <= tolerance[curr]:
        res = "قمة_الملقط_هابط"
    elif direction[prev] == -1 and direction[curr] == 1 and abs(lo[curr] - lo[prev]) <= tolerance[curr]:
        res = "قاع_الملقط_صاعد"

    # Thrusting Line (خط الدفع - هابط)
    elif direction[prev] == -1 and direction[curr] == 1 and \
         op[curr] < lo[prev] and cl[curr] > cl[prev] and cl[curr] < (op[prev] + cl[prev])/2:
        res = "خط_الدفع_هابط"

    # Doji Star (نجمة الدوجي - بداية انعكاس)
    elif is_long_body[prev] and is_doji[curr]:
        if direction[prev] == 1 and lo[curr] > hi[prev]:
            res = "نجمة_دوجي_هابط"
        elif direction[prev] == -1 and hi[curr] < lo[prev]:
            res = "نجمة_دوجي_صاعد"

    # ==========================================
    # --- 5. الأنماط الفردية (1 Candle) ---
    # ==========================================
    
    # تم وضع شروط المطرقة ضمن سلسلة الـ elif لمنعها من الكتابة فوق الأنماط الثنائية أو الثلاثية
    elif is_hammer_type[curr]:
        res = "مطرقة_صاعد" if prev_trend == -1 else "الرجل_المشنوق_هابط"
    elif is_star_type[curr]:
        res = "مطرقة_مقلوبة_صاعد" if prev_trend == -1 else "نجمة_الشهاب_هابط"
        
    # Belt Hold (الحزام الممسوك)
    elif direction[curr] == 1 and is_long_body[curr] and lower_wick[curr] <= tolerance[curr]:
        res = "الحزام_الممسوك_صاعد"
    elif direction[curr] == -1 and is_long_body[curr] and upper_wick[curr] <= tolerance[curr]:
        res = "الحزام_الممسوك_هابط"
    
    elif is_dragon_doji[curr]: res = "دوجي_التنين_صاعد"
    elif is_gravestone_doji[curr]: res = "دوجي_شاهد_القبر_هابط"
    elif is_doji[curr]: res = "Neutral_Doji"
    elif is_marubozu[curr]: res = "ماروبوزو_صاعد" if direction[curr] == 1 else "ماروبوزو_هابط"
    elif is_spinning_top[curr]: res = "Spinning_Top"

    return res
    

# ==========================================
# --- [ 📡 الرادار الذكي: قناص الفجوات والسيولة ] ---
# ==========================================
def extract_smart_money_concepts(df):
    if len(df) < 25:
        return {"fvg": "None", "volume_anomaly": False, "strict_pattern": "None"}
    
    # 1. الفجوات العادلة (تحويل صريح لـ bool)
    bullish_fvg = bool(df['low'].iloc[-1] > df['high'].iloc[-3])
    bearish_fvg = bool(df['high'].iloc[-1] < df['low'].iloc[-3])
    
    # 2. انفجار السيولة (هنا غالباً يقع الخطأ بسبب المتوسط)
    vol_sma_20 = df['volume'].iloc[-21:-1].mean()
    current_vol = df['volume'].iloc[-1]
    volume_anomaly = bool(current_vol >= (vol_sma_20 * 2))
    
    # 3. الأنماط الصارمة
    body = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
    upper_wick = df['high'].iloc[-1] - max(df['open'].iloc[-1], df['close'].iloc[-1])
    lower_wick = min(df['open'].iloc[-1], df['close'].iloc[-1]) - df['low'].iloc[-1]
    
    strict_pattern = "None"
    if lower_wick >= (2 * body) and upper_wick <= (0.2 * body) and body > 0:
        strict_pattern = "Strict_Hammer"
    elif upper_wick >= (2 * body) and lower_wick <= (0.2 * body) and body > 0:
        strict_pattern = "Strict_Shooting_Star"

    fvg_status = "Bullish_FVG" if bullish_fvg else "Bearish_FVG" if bearish_fvg else "None"
    
    return {
        "fvg": fvg_status,
        "volume_anomaly": volume_anomaly,
        "strict_pattern": strict_pattern
    }


def detect_divergence(prices, indicators):
    """
    🕵️‍♂️ كاشف الانحرافات (Divergence Detector)
    يقارن بين قمم السعر وقمم المؤشر (RSI/OBV) لكشف التلاعب أو ضعف الاتجاه.
    """
    if len(prices) < 5 or len(indicators) < 5:
        return "Normal"

    try:
        # قمة السعر الحالية مقارنة بالسابقة
        price_higher_high = prices[-1] > prices[-5]
        price_lower_low = prices[-1] < prices[-5]

        # قمة المؤشر الحالية مقارنة بالسابقة
        ind_higher_high = indicators[-1] > indicators[-5]
        ind_lower_low = indicators[-1] < indicators[-5]

        # 1. انحراف سلبي (Bearish Divergence): السعر يصعد والمؤشر يهبط
        if price_higher_high and not ind_higher_high:
            return "Bearish Divergence"

        # 2. انحراف إيجابي (Bullish Divergence): السعر يهبط والمؤشر يصعد
        if price_lower_low and not ind_lower_low:
            return "Bullish Divergence"

        return "Normal"
    except Exception:
        return "Normal"


def calculate_macd_values(closes, fast=12, slow=26, signal=9):
    try:
        s = pd.Series(closes)
        ema_fast = s.ewm(span=fast, adjust=False).mean()
        ema_slow = s.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        # التأكد التام من تحويلها لأرقام بايثون الصافية
        return {
            "macd": float(macd_line.values[-1]) if len(macd_line) > 0 else 0.0,
            "signal": float(signal_line.values[-1]) if len(signal_line) > 0 else 0.0,
            "hist": float(histogram.values[-1]) if len(histogram) > 0 else 0.0
        }
    except Exception as e:
        print(f"❌ خطأ في الحساب اليدوي للماكد: {e}")
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}

# ==========================================
# 1. دالة استخراج الدعوم والمقاومات (المحدثة)
# ==========================================

def calculate_price_action_sr(highs, lows, return_swings=False):
    """
    تستخرج أحدث دعم وأحدث مقاومة، مع إمكانية إرجاع كافة القمم والقيعان (Swings)
    لدعم حساب القنوات السعرية في مشروع Trade Reaper.
    """
    supports = []     # ستخزن الآن: (الفهرس، السعر)
    resistances = []  # ستخزن الآن: (الفهرس، السعر)

    # استخراج القيعان والقمم الحقيقية (شمعتين يمين وشمعتين يسار للفلترة الصارمة)
    for i in range(2, len(highs) - 2):
        # القاع الحقيقي
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            supports.append((i, lows[i])) # حفظ الفهرس والسعر كزوج (tuple)
            
        # القمة الحقيقية
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistances.append((i, highs[i])) # حفظ الفهرس والسعر كزوج (tuple)

    # --- الجزء المضاف لحل مشكلة القنوات السعرية ---
    if return_swings:
        # نعيد القوائم كاملة (الفهرس والسعر) لكي تستطيع دالة القنوات رسم التوازي
        return resistances, supports 

    # استخراج الأحدث (للمحافظة على عمل الكود القديم وتحديث قاعدة البيانات)
    # نأخذ القيمة السعرية فقط [1] من آخر عنصر سجلناه
    latest_support = supports[-1][1] if supports else None
    latest_resistance = resistances[-1][1] if resistances else None

    return latest_support, latest_resistance


def get_imbalance_ratio(depth_data):
    """
    تحويل بيانات دفتر الأوامر الخام إلى نسبة اختلال السيولة.
    depth_data: هي النتيجة القادمة من exchange.fetch_order_book
    """
    try:
        # تحويل القوائم إلى مصفوفات Numpy لمعالجة سريعة جداً
        # نأخذ أول 20 مستوى (أهم مستويات السيولة القريبة من السعر)
        bids = np.array(depth_data['bids'][:20]) 
        asks = np.array(depth_data['asks'][:20])
        
        # جمع كميات الشراء (العمود الثاني في المصفوفة)
        total_bids_volume = np.sum(bids[:, 1])
        
        # جمع كميات البيع (العمود الثاني في المصفوفة)
        total_asks_volume = np.sum(asks[:, 1])
        
        # حساب النسبة النهائية
        if total_asks_volume > 0:
            ratio = total_bids_volume / total_asks_volume
        else:
            ratio = 1.0 # قيمة افتراضية في حال تعطل البيانات
            
        return float(ratio)
    except Exception as e:
        return 1.0

# ==========================================
# 1. دوال المساعدة، المؤشرات، والدقة الرياضية المتقدمة
# ==========================================

def calculate_log_fib_accuracy(actual_price: float, target_price: float, atr_value: float) -> float:
    """
    حساب الدقة باستخدام المقياس اللوغاريتمي ونسبة سماح تعتمد على معدل التذبذب (ATR)
    بدلاً من نسبة مئوية ثابتة.
    """
    if target_price == 0: return 0.0
    
    # حساب الانحراف اللوغاريتمي
    log_deviation = abs(np.log(actual_price / target_price))
    
    # التسامح الديناميكي بناءً على تقلبات السوق (ATR)
    dynamic_tolerance = atr_value / target_price 
    
    # حماية من القسمة على صفر في حالة انعدام السيولة التام
    if dynamic_tolerance == 0:
        return 100.0 if log_deviation == 0 else 0.0
        
    if log_deviation > dynamic_tolerance * 2:
        return 0.0 # بعيد جداً عن منطقة الانعكاس
        
    # دالة غاوسية (Gaussian) لحساب الدقة بحيث تكون 100% في المركز وتقل بانحناء طبيعي
    accuracy = np.exp(-0.5 * (log_deviation / (dynamic_tolerance / 2))**2)
    return round(accuracy * 100, 2)

def calculate_statistical_trend(x_coords: np.ndarray, y_coords: np.ndarray):
    """
    استخدام الانحدار الخطي (OLS) لإيجاد خط الترند الأقوى رياضياً،
    وحساب R-squared لمعرفة مدى "مثالية" هذا الترند.
    """
    if len(x_coords) < 3:
        return {"slope": 0, "intercept": 0, "r_squared": 0, "is_valid": False}
        
    slope, intercept, r_value, p_value, std_err = linregress(x_coords, y_coords)
    r_squared = r_value ** 2 # معامل التحديد
    
    # نعتبر الترند قوياً إذا كان R-squared أكبر من 0.85
    is_valid = True if r_squared >= 0.85 else False
    
    return {
        "slope": slope,
        "intercept": intercept,
        "r_squared": round(r_squared, 4),
        "is_valid": is_valid
    }

def is_near_ratio(value: float, target: float, tolerance: float = 0.02) -> bool:
    return abs(value - target) <= tolerance


def calculate_exact_accuracy(actual: float, target: float) -> float:
    """حساب الدقة المئوية لنسبة الفيبوناتشي"""
    if target == 0: return 0.0
    acc = 1.0 - (abs(actual - target) / target)
    return round(max(0, acc) * 100, 2)


def calculate_rsi(series, period: int = 14):
    """حساب مؤشر القوة النسبية (RSI) بشكل آمن"""
    # تحويل البيانات إلى Series إذا كانت قائمة (List) لتجنب خطأ 'list' object has no attribute 'diff'
    if isinstance(series, list):
        series = pd.Series(series)
    
    delta = series.diff()
    
    # حساب المكاسب والخسائر
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    
    # التعامل مع حالة القسمة على صفر إذا كانت الخسائر صفراً
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def detect_rsi_divergence_4h(df_4h: pd.DataFrame) -> str:
    """اكتشاف الدايفرجنس باستخدام فريم 4 ساعات ومستويات السيولة العميقة (78/22)"""
    if df_4h is None or len(df_4h) < 50:
        return "NONE"
    
    df = df_4h.copy()
    if 'rsi' not in df.columns:
        df['rsi'] = calculate_rsi(df['close'])
        
    highs, lows = df['high'].values, df['low'].values
    rsis = df['rsi'].values
    
    price_peaks, _ = find_peaks(highs, distance=5)
    price_troughs, _ = find_peaks(-lows, distance=5)
    
    if len(price_peaks) >= 2 and len(price_troughs) >= 2:
        p1, p2 = price_peaks[-2], price_peaks[-1]
        if highs[p2] > highs[p1] and rsis[p2] < rsis[p1] and (rsis[p1] >= 78 or rsis[p2] >= 78):
            return "BEARISH_DIVERGENCE"
            
        t1, t2 = price_troughs[-2], price_troughs[-1]
        if lows[t2] < lows[t1] and rsis[t2] > rsis[t1] and (rsis[t1] <= 22 or rsis[t2] <= 22):
            return "BULLISH_DIVERGENCE"
            
    return "NONE"


def calculate_marubozu_status(open_p: float, high_p: float, low_p: float, close_p: float) -> int:
    """تحديد ما إذا كانت شمعة الاختراق ماروبوزو (1: نعم، 2: لا)"""
    body = abs(close_p - open_p)
    wick = high_p - low_p
    if wick == 0: return 2
    return 1 if (body / wick) >= 0.85 else 2

def check_ema_confluence(df: pd.DataFrame, target_price: float, tolerance_pct: float = 0.005) -> int:
    """تأكيد التوافق (Confluence) مع متوسط متحرك صارم (EMA 50)"""
    if len(df) < 50: return 2
    ema_50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    return 1 if abs(target_price - ema_50) / ema_50 <= tolerance_pct else 2

# ==========================================
# 2. محرك الهارمونيك المطور (EliteTradingEngine)
# ==========================================
def calculate_harmonic_targets(
    pattern_name: str, direction: str, point_d: float, point_a: float, point_x: float,
    accuracy: float = 0.0, confluence: int = 2, pattern_type: str = "standard"
) -> Dict[str, Union[str, float, int]]:
    
    ad_length = abs(point_a - point_d)
    ratio = 0.618 if pattern_type == "standard" else 0.50 
    
    if direction == "شراء":
        target = point_d + (ad_length * ratio) 
        sl = point_x - (point_x * 0.002) 
    else:
        target = point_d - (ad_length * ratio)
        sl = point_x + (point_x * 0.002)

    return {
        "name": pattern_name,
        "class": "هارمونيك احترافي",
        "breakout": round(point_d, 5), 
        "target": round(target, 5),
        "sl": round(sl, 5),
        "status": "مكتمل",
        "harmonic_fib_accuracy": accuracy,
        "harmonic_d_confluence": confluence
    }
   

def detect_elite_patterns(
    df: pd.DataFrame, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, 
    current_price: float, tolerance: float = 0.02
) -> Dict[str, Union[str, float, int]]:
    
    default_pattern = {
        "name": "لا يوجد", "class": "لا يوجد", "breakout": 0.0, "target": 0.0, 
        "sl": 0.0, "status": "بحث مستمر", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2
    }

    # 1. حساب ATR لضبط دقة الفيبوناتشي اللوغاريتمية
    atr_value = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]

    peaks, _ = find_peaks(highs, distance=5)
    troughs, _ = find_peaks(-lows, distance=5)
    
    if len(peaks) < 3 or len(troughs) < 3:
        return default_pattern

    p, t = highs[peaks], lows[troughs]
    p1, p2, p3 = p[-3], p[-2], p[-1]
    t1, t2, t3 = t[-3], t[-2], t[-1]
    
    # ---------------------------------------------------------
    # 1. السايفر (Cypher)
    # ---------------------------------------------------------
    if len(p) >= 2 and len(t) >= 2:
        # شرائي
        X, A, B, C = t[-2], p[-2], t[-1], p[-1]
        xa = A - X
        if xa != 0:
            b_ret, c_ext = (A - B) / xa, (C - X) / xa
            if (0.382 <= b_ret <= 0.618) and (1.272 <= c_ext <= 1.414):
                d_target = C - (abs(C - B) * 0.786)
                acc = calculate_log_fib_accuracy(current_price, d_target, atr_value)
                conf = check_ema_confluence(df, d_target)
                return calculate_harmonic_targets("سايفر شرائي", "شراء", d_target, C, X, acc, conf, "standard")

        # بيعي
        X, A, B, C = p[-2], t[-2], p[-1], t[-1]
        xa = X - A
        if xa != 0:
            b_ret, c_ext = (B - A) / xa, (X - C) / xa
            if (0.382 <= b_ret <= 0.618) and (1.272 <= c_ext <= 1.414):
                d_target = C + (abs(B - C) * 0.786)
                acc = calculate_log_fib_accuracy(current_price, d_target, atr_value)
                conf = check_ema_confluence(df, d_target)
                return calculate_harmonic_targets("سايفر بيعي", "بيع", d_target, C, X, acc, conf, "standard")

    # ---------------------------------------------------------
    # 2. القرش (Shark)
    # ---------------------------------------------------------
    # شرائي
    if len(t) >= 3 and len(p) >= 2:
        O, X, A, B, C = t[-3], p[-2], t[-2], p[-1], t[-1]
        ox, xa, ab, bc = (X-O), (X-A), (B-A), (B-C)
        if xa != 0 and 1.13 <= (ab/xa) <= 1.618:
            if ox != 0 and is_near_ratio(bc/ox, 0.886, tolerance):
                acc = calculate_log_fib_accuracy(current_price, C, atr_value)
                conf = check_ema_confluence(df, C)
                return calculate_harmonic_targets("قرش شرائي", "شراء", C, B, O, acc, conf, "shark")

    # بيعي
    if len(p) >= 3 and len(t) >= 2:
        O, X, A, B, C = p[-3], t[-2], p[-2], t[-1], p[-1]
        ox, xa, ab, bc = (O-X), (A-X), (A-B), (C-B)
        if xa != 0 and 1.13 <= (ab/xa) <= 1.618:
            if ox != 0 and is_near_ratio(bc/ox, 0.886, tolerance):
                acc = calculate_log_fib_accuracy(current_price, C, atr_value)
                conf = check_ema_confluence(df, C)
                return calculate_harmonic_targets("قرش بيعي", "بيع", C, B, O, acc, conf, "shark")

    # ---------------------------------------------------------
    # 3. الجارتلي والخفاش (Gartley & Bat)
    # ---------------------------------------------------------
    # شرائي
    if len(t) >= 3 and len(p) >= 2:
        X, A, B, C, D = t[-3], p[-2], t[-2], p[-1], t[-1]
        xa, ab, ad = (A-X), (A-B), (A-D)
        if xa != 0:
            actual_ab, actual_ad = ab/xa, ad/xa
            if is_near_ratio(actual_ab, 0.618, tolerance) and is_near_ratio(actual_ad, 0.786, tolerance):
                acc = calculate_log_fib_accuracy(current_price, D, atr_value)
                conf = check_ema_confluence(df, D)
                return calculate_harmonic_targets("جارتلي شرائي", "شراء", D, A, X, acc, conf)
            if (0.382 <= actual_ab <= 0.5) and is_near_ratio(actual_ad, 0.886, tolerance):
                acc = calculate_log_fib_accuracy(current_price, D, atr_value)
                conf = check_ema_confluence(df, D)
                return calculate_harmonic_targets("خفاش شرائي", "شراء", D, A, X, acc, conf)

    # بيعي
    if len(p) >= 3 and len(t) >= 2:
        X, A, B, C, D = p[-3], t[-2], p[-2], t[-1], p[-1]
        xa, ab, ad = (X-A), (B-A), (D-A)
        if xa != 0:
            actual_ab, actual_ad = ab/xa, ad/xa
            if is_near_ratio(actual_ab, 0.618, tolerance) and is_near_ratio(actual_ad, 0.786, tolerance):
                acc = calculate_log_fib_accuracy(current_price, D, atr_value)
                conf = check_ema_confluence(df, D)
                return calculate_harmonic_targets("جارتلي بيعي", "بيع", D, A, X, acc, conf)
            if (0.382 <= actual_ab <= 0.5) and is_near_ratio(actual_ad, 0.886, tolerance):
                acc = calculate_log_fib_accuracy(current_price, D, atr_value)
                conf = check_ema_confluence(df, D)
                return calculate_harmonic_targets("خفاش بيعي", "بيع", D, A, X, acc, conf)

 
    # ---------------------------------------------------------
    # 4. النماذج الهيكلية والاستمرارية (إصلاح البوق وإضافة الأعلام والرايات)
    # ---------------------------------------------------------
    
    # 1. البوق المتسع (Megaphone) - تم تخفيف الصرامة الرياضية ليناسب الكريبتو
    # يكفي أن تكون القمة الأخيرة أعلى من السابقة والقاع الأخير أدنى من السابق
    if p3 > (p2 * 1.002) and t3 < (t2 * 0.998): 
        megaphone_height = p3 - t3
        if current_price > p3:
            return {"name": "بوق متسع صاعد", "class": "انفجار سعري", "breakout": round(p3, 5), "target": round(p3 + (megaphone_height * 0.8), 5), "sl": round(p3 - (megaphone_height * 0.3), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}
        elif current_price < t3:
            return {"name": "بوق متسع هابط", "class": "انهيار سعري", "breakout": round(t3, 5), "target": round(t3 - (megaphone_height * 0.8), 5), "sl": round(t3 + (megaphone_height * 0.3), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}

    # 2. اكتشاف الأعلام والرايات (Flags & Pennants)
    # الفكرة: حركة قوية (عمود) تليها قمتين وقاعين في نطاق ضيق (التصحيح)
    pole_height = max(p1, p2) - min(t1, t2)
    consolidation_height = p3 - t3
    
    if pole_height > 0 and consolidation_height > 0:
        if consolidation_height < (pole_height * 0.5): # التذبذب أقل من نصف طول العمود (مهم جداً)
            
            # الراية (Pennant): القمم تنزل والقيعان ترتفع (شبه مثلث متماثل صغير)
            if p3 < p2 and t3 > t2:
                if current_price > p3: # اختراق لأعلى
                    return {"name": "راية صاعدة", "class": "اختراق استمراري", "breakout": round(p3, 5), "target": round(p3 + pole_height, 5), "sl": round(t3 - (pole_height * 0.1), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}
                elif current_price < t3: # كسر لأسفل
                    return {"name": "راية هابطة", "class": "كسر استمراري", "breakout": round(t3, 5), "target": round(t3 - pole_height, 5), "sl": round(p3 + (pole_height * 0.1), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}
            
            # العلم (Flag): القمم تنزل والقيعان تنزل بمسار متوازي (تصحيح عكس الاتجاه)
            elif p3 < p2 and t3 < t2 and is_near_ratio((p2-p3), (t2-t3), tolerance=0.05):
                if current_price > p3:
                    return {"name": "علم صاعد", "class": "اختراق استمراري", "breakout": round(p3, 5), "target": round(p3 + pole_height, 5), "sl": round(t3, 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}
                elif current_price < t3:
                    return {"name": "علم هابط", "class": "كسر استمراري", "breakout": round(t3, 5), "target": round(t3 - pole_height, 5), "sl": round(p3, 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}

    # القمة الثلاثية
    if is_near_ratio(p1/p2, 1, tolerance) and is_near_ratio(p2/p3, 1, tolerance):
        neckline = min(lows[peaks[-3]:peaks[-1]])
        if current_price < neckline:
            height = max(p1, p2, p3) - neckline
            return {"name": "قمة ثلاثية", "class": "انعكاسي هابط", "breakout": round(neckline, 5), "target": round(neckline - height, 5), "sl": round(neckline + (height * 0.3), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}

    # القاع الثلاثي
    if is_near_ratio(t1/t2, 1, tolerance) and is_near_ratio(t2/t3, 1, tolerance):
        neckline = max(highs[troughs[-3]:troughs[-1]])
        if current_price > neckline:
            height = neckline - min(t1, t2, t3)
            return {"name": "قاع ثلاثي", "class": "انعكاسي صاعد", "breakout": round(neckline, 5), "target": round(neckline + height, 5), "sl": round(neckline - (height * 0.3), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}

    # صندوق دارفاس
    if is_near_ratio(p2, p3, p2*tolerance) and is_near_ratio(t2, t3, t2*tolerance):
        box_high = max(p2, p3)
        box_low = min(t2, t3)
        box_height = box_high - box_low
        if current_price > box_high:
            return {"name": "صندوق دارفاس صاعد", "class": "اختراق استمراري", "breakout": round(box_high, 5), "target": round(box_high + box_height, 5), "sl": round(box_high - (box_height * 0.5), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}
        elif current_price < box_low:
            return {"name": "صندوق دارفاس هابط", "class": "كسر استمراري", "breakout": round(box_low, 5), "target": round(box_low - box_height, 5), "sl": round(box_low + (box_height * 0.5), 5), "status": "مكتمل", "harmonic_fib_accuracy": 0.0, "harmonic_d_confluence": 2}

    return default_pattern

# ==========================================
# 3. دوال تحليل الترند والزاوية والقنوات
# ==========================================

def find_swing_points(df, window=5):
    highs, lows = df['high'].values, df['low'].values
    swing_highs, swing_lows = [], []
    for i in range(window, len(df) - window):
        if highs[i] == max(highs[i - window : i + window + 1]):
            swing_highs.append((i, highs[i]))
        if lows[i] == min(lows[i - window : i + window + 1]):
            swing_lows.append((i, lows[i]))
    return swing_highs, swing_lows


def calculate_trendline_angle(x1, y1, x2, y2, avg_price):
    dx = x2 - x1
    if dx == 0: return 90
    dy = ((y2 - y1) / avg_price) * 100  
    angle_rad = math.atan(dy / dx)
    return abs(math.degrees(angle_rad))


def validate_strict_trendline(df, x1, y1, x2, y2, trend_type="UP"):
    slope = (y2 - y1) / (x2 - x1)
    intercept = y1 - (slope * x1)
    for i in range(x1 + 1, len(df)):
        trend_price = (slope * i) + intercept 
        body_bottom = min(df['open'].iloc[i], df['close'].iloc[i])
        body_top = max(df['open'].iloc[i], df['close'].iloc[i])
        if trend_type == "UP" and body_bottom < trend_price: return False 
        elif trend_type == "DOWN" and body_top > trend_price: return False                
    return True
    

def generate_trend_data(df, min_distance=10):
    swings_high, swings_low = find_swing_points(df, window=5)
    avg_price = df['close'].mean()
    touch_tolerance = avg_price * 0.001 
    
    best_trend = {
        "direction": "عرضي", "angle": 0.0, "touches": 0, 
        "current_line_price": 0.0, "is_valid": 2, "slope": 0.0, 
        "intercept": 0.0, "r_squared": 0.0 # إضافة معامل التحديد هنا
    }
    
    last_idx = len(df) - 1

    # --- 1. البحث عن ترند صاعد (عبر القيعان Swings Low) ---
    if len(swings_low) >= 2:
        for i in range(len(swings_low)-1, 0, -1):
            for j in range(i-1, -1, -1):
                x2, y2 = swings_low[i]
                x1, y1 = swings_low[j]
                if (x2 - x1) < min_distance or y2 <= y1: continue
                
                slope = (y2 - y1) / (x2 - x1)
                intercept = y1 - (slope * x1)
                
                if validate_strict_trendline(df, x1, y1, x2, y2, "UP"):
                    angle = calculate_trendline_angle(x1, y1, x2, y2, avg_price)
                    
                    if 15 <= angle <= 65:
                        # --- [هنا يبدأ التبني!] ---
                        # جمع النقاط التي تلمس الخط فعلياً لاختبارها إحصائياً
                        pts_x, pts_y = [], []
                        for sx, sy in swings_low:
                            expected_y = (slope * sx) + intercept
                            if abs(sy - expected_y) <= touch_tolerance:
                                pts_x.append(sx)
                                pts_y.append(sy)
                        
                        # استدعاء الدالة اليتيمة لتحليل الترند إحصائياً
                        stats = calculate_statistical_trend(np.array(pts_x), np.array(pts_y))
                        
                        # تحديث أفضل ترند إذا كان إحصائياً أقوى (R-squared أعلى)
                        if len(pts_x) >= 2 and stats["r_squared"] > best_trend["r_squared"]:
                            best_trend.update({
                                "direction": "صاعد",
                                "angle": round(angle, 2),
                                "touches": len(pts_x),
                                "is_valid": 1 if (len(pts_x) >= 3 and stats["is_valid"]) else 2,
                                "slope": slope,
                                "intercept": intercept,
                                "current_line_price": round((slope * last_idx) + intercept, 5),
                                "r_squared": stats["r_squared"]
                            })

    # --- 2. البحث عن ترند هابط (عبر القمم Swings High) ---
    if len(swings_high) >= 2:
        for i in range(len(swings_high)-1, 0, -1):
            for j in range(i-1, -1, -1):
                x2, y2 = swings_high[i]
                x1, y1 = swings_high[j]
                if (x2 - x1) < min_distance or y2 >= y1: continue
                
                slope = (y2 - y1) / (x2 - x1)
                intercept = y1 - (slope * x1)
                
                if validate_strict_trendline(df, x1, y1, x2, y2, "DOWN"):
                    angle = calculate_trendline_angle(x1, y1, x2, y2, avg_price)
                    
                    if 15 <= angle <= 65:
                        # --- [هنا يبدأ التبني!] ---
                        pts_x, pts_y = [], []
                        for sx, sy in swings_high:
                            expected_y = (slope * sx) + intercept
                            if abs(sy - expected_y) <= touch_tolerance:
                                pts_x.append(sx)
                                pts_y.append(sy)
                        
                        stats = calculate_statistical_trend(np.array(pts_x), np.array(pts_y))

                        if len(pts_x) >= 2 and stats["r_squared"] > best_trend["r_squared"]:
                            best_trend.update({
                                "direction": "هابط",
                                "angle": round(angle, 2),
                                "touches": len(pts_x),
                                "is_valid": 1 if (len(pts_x) >= 3 and stats["is_valid"]) else 2,
                                "slope": slope,
                                "intercept": intercept,
                                "current_line_price": round((slope * last_idx) + intercept, 5),
                                "r_squared": stats["r_squared"]
                            })

    return best_trend, swings_high, swings_low
    

def calculate_price_channel(df, best_trend, swings_high, swings_low):
    """
    تحديث احترافي: يقوم ببناء قناة سعرية موازية للترند المكتشف،
    ويحسب عدد اللمسات على الخط المقابل لضمان صحة القناة كلاسيكياً.
    """
    # 1. الإعدادات الأولية
    channel_data = {
        "channel_upper": 0.0, 
        "channel_lower": 0.0, 
        "channel_direction": best_trend.get("direction", "عرضي"),
        "channel_touches": 0,
        "channel_status": "NONE",
        "channel_weakness": "NONE"
    }

    # التأكد من وجود ترند صحيح لبناء القناة عليه
    if best_trend.get("is_valid") != 1 or best_trend.get("slope") == 0:
        return channel_data

    m = best_trend["slope"]
    b_base = best_trend.get("intercept", 0.0)
    avg_price = df['close'].mean()
    touch_tolerance = avg_price * 0.0015  # نسبة سماح 0.15% لتغطية ذيول الشموع
    last_x = len(df) - 1

    # 2. منطق البحث عن الخط الموازي (السقف أو القاع المقابل)
    best_intercept_opp = None
    max_opp_touches = 0
    
    # إذا كان الترند صاعداً (قاعدته القيعان)، نبحث عن أفضل سقف يمر بالقمم
    if best_trend["direction"] == "صاعد":
        target_swings = swings_high
        # السعر السفلي للقناة (الترند الأساسي)
        channel_data["channel_lower"] = round((m * last_x) + b_base, 5)
        
        for sx, sy in target_swings:
            current_b_opp = sy - (m * sx)
            # حساب كم نقطة تلمس هذا الخط الموازي
            touches = sum(1 for tx, ty in target_swings if abs(ty - ((m * tx) + current_b_opp)) <= touch_tolerance)
            if touches > max_opp_touches:
                max_opp_touches = touches
                best_intercept_opp = current_b_opp
        
        if best_intercept_opp is not None:
            channel_data["channel_upper"] = round((m * last_x) + best_intercept_opp, 5)

    # إذا كان الترند هابطاً (قاعدته القمم)، نبحث عن أفضل قاع يمر بالقيعان
    elif best_trend["direction"] == "هابط":
        target_swings = swings_low
        # السعر العلوي للقناة (الترند الأساسي)
        channel_data["channel_upper"] = round((m * last_x) + b_base, 5)
        
        for sx, sy in target_swings:
            current_b_opp = sy - (m * sx)
            touches = sum(1 for tx, ty in target_swings if abs(ty - ((m * tx) + current_b_opp)) <= touch_tolerance)
            if touches > max_opp_touches:
                max_opp_touches = touches
                best_intercept_opp = current_b_opp
                
        if best_intercept_opp is not None:
            channel_data["channel_lower"] = round((m * last_x) + best_intercept_opp, 5)

    # 3. تقييم جودة القناة (اللمسات والحالة)
    total_touches = best_trend.get("touches", 2) + max_opp_touches
    channel_data["channel_touches"] = total_touches
    
    if total_touches >= 5: # 3 من جهة و 2 من جهة أخرى مثلاً
        channel_data["channel_status"] = "STRONG_CONFIRMED"
    elif total_touches >= 3:
        channel_data["channel_status"] = "VALID"
    else:
        channel_data["channel_status"] = "WEAK"

    # 4. دمج تحليل الضعف (RSI) من كودك القديم كفلتر إضافي
    if 'rsi' not in df.columns:
        df['rsi'] = calculate_rsi(df['close'])
    current_rsi = df['rsi'].iloc[-1]
    
    if best_trend["direction"] == "صاعد" and current_rsi < 45:
        channel_data["channel_weakness"] = "BULLISH_EXHAUSTION" # إرهاق شرائي
    elif best_trend["direction"] == "هابط" and current_rsi > 55:
        channel_data["channel_weakness"] = "BEARISH_EXHAUSTION" # إرهاق بيعي

    return channel_data

# ==========================================
# 4. دمج المحرك والمخرجات الشاملة
# ==========================================
def calculate_continuation_logic(pattern_name: str, prior_trend: str, breakout_point: float, pattern_high: float, pattern_low: float) -> dict:
    height = pattern_high - pattern_low
    
    # 1. تحديد الأهداف بناءً على الاتجاه (شراء أو بيع)
    if prior_trend == "شراء":
        target = breakout_point + height
        sl = breakout_point - (height * 0.5)
        status_class = "استمراري صاعد" # تخصيص الاسم للحالة الشرائية
    else:
        target = breakout_point - height
        sl = breakout_point + (height * 0.5)
        status_class = "استمراري هابط" # تخصيص الاسم للحالة البيعية

    # 2. إرجاع النتائج مع استخدام status_class بدلاً من النص الثابت
    return {
        "name": pattern_name, 
        "class": status_class, # هنا سيتغير النص حسب نوع الصفقة
        "breakout": round(breakout_point, 5), 
        "target": round(target, 5), 
        "sl": round(sl, 5), 
        "pattern_high": pattern_high, 
        "pattern_low": pattern_low
    }



def detect_patterns_and_calculate(
    df_tf: pd.DataFrame, symbol: str, tf: str, df_4h: pd.DataFrame = None, 
    min_bars: int = 20, trend_threshold: float = 0.03, tolerance: float = 0.02, strict_breakout: bool = True
) -> Dict[str, Union[str, float, int]]:
    
    final_output = {
        "name": "لا يوجد", "class": "لا يوجد", "breakout": 0.0, "target": 0.0, "sl": 0.0, "status": "بحث مستمر",
        "is_body_close": 2,
        "channel_weakness": "NONE",
        "pattern_retracement_pct": 0.0,
        "pattern_apex_progress": 0.0,
        "is_marubozu_breakout": 2,
        "rsi_divergence_4h": "NONE",
        "harmonic_fib_accuracy": 0.0,
        "harmonic_d_confluence": 2,
        "1h_trend_angle": 0.0
    }

    if df_tf is None or len(df_tf) < min_bars: return final_output

    highs, lows, closes = df_tf['high'].values, df_tf['low'].values, df_tf['close'].values
    opens = df_tf['open'].values
    current_price = closes[-2] if strict_breakout else closes[-1]
    current_candle_idx = -2 if strict_breakout else -1
    
    # 1. الترند والزاوية والقنوات
    trend_data, s_highs, s_lows = generate_trend_data(df_tf)
    final_output["1h_trend_angle"] = trend_data["angle"]
    
    channel_data = calculate_price_channel(df_tf, trend_data, s_highs, s_lows)
    final_output["channel_weakness"] = channel_data["channel_weakness"]

    final_output["rsi_divergence_4h"] = detect_rsi_divergence_4h(df_4h)

    # 2. محرك النماذج (Elite Patterns)
    detected_pattern = detect_elite_patterns(df_tf, highs, lows, closes, current_price, tolerance)
    
    # 3. النماذج الكلاسيكية (في حال لم يتم العثور على هارمونيك/هيكلي)
    if detected_pattern["name"] == "لا يوجد":
        peaks, _ = find_peaks(highs, distance=5)
        troughs, _ = find_peaks(-lows, distance=5)
        
        # باقي النماذج الكلاسيكية
        if detected_pattern["name"] == "لا يوجد" and len(peaks) >= 3 and len(troughs) >= 3:
            p1, p2, p3 = highs[peaks[-3]], highs[peaks[-2]], highs[peaks[-1]]
            t1, t2, t3 = lows[troughs[-3]], lows[troughs[-2]], lows[troughs[-1]]
            
            # قمة مزدوجة
            if is_near_ratio(p2/p3, 1, tolerance):
                neckline = t2
                if current_price < neckline:
                    height = max(p2, p3) - neckline
                    detected_pattern = {"name": "قمة مزدوجة", "class": "انعكاسي هابط", "breakout": round(neckline, 5), "target": round(neckline - height, 5), "sl": round(neckline + (height * 0.3), 5)}
            
            # قاع مزدوج
            elif is_near_ratio(t2/t3, 1, tolerance):
                neckline = p2
                if current_price > neckline:
                    height = neckline - min(t2, t3)
                    detected_pattern = {"name": "قاع مزدوج", "class": "انعكاسي صاعد", "breakout": round(neckline, 5), "target": round(neckline + height, 5), "sl": round(neckline - (height * 0.3), 5)}
            
            # رأس وكتفين
            elif p2 > p1 and p2 > p3 and is_near_ratio(p1/p3, 1, tolerance*2):
                neckline = (t1 + t2) / 2
                if current_price < neckline:
                    height = p2 - neckline
                    detected_pattern = {"name": "رأس وكتفين", "class": "انعكاسي هابط", "breakout": round(neckline, 5), "target": round(neckline - height, 5), "sl": round(p3, 5)}
            
            # رأس وكتفين مقلوب
            elif t2 < t1 and t2 < t3 and is_near_ratio(t1/t3, 1, tolerance*2):
                neckline = (p1 + p2) / 2
                if current_price > neckline:
                    height = neckline - t2
                    detected_pattern = {"name": "رأس وكتفين مقلوب", "class": "انعكاسي صاعد", "breakout": round(neckline, 5), "target": round(neckline + height, 5), "sl": round(t3, 5)}
            
            # المثلثات والأوتاد
            elif p3 < p2 and t3 > t2:
                if current_price > p3: 
                    detected_pattern = calculate_continuation_logic("مثلث متماثل صاعد", "شراء", p3, p2, t2)
                elif current_price < t3: 
                    detected_pattern = calculate_continuation_logic("مثلث متماثل هابط", "بيع", t3, p2, t2)
                
                if detected_pattern.get("name", "لا يوجد") != "لا يوجد":
                    start_idx = min(peaks[-2], troughs[-2])
                    est_apex = start_idx + (len(df_tf) - start_idx) * 1.5
                    if est_apex > start_idx:
                        progress = (len(df_tf) - start_idx) / (est_apex - start_idx)
                        final_output["pattern_apex_progress"] = round(min(1.0, progress) * 100, 2)
            
            # وتد هابط / صاعد
            elif p3 < p2 < p1 and t3 < t2 < t1:
                if current_price > p3:
                    detected_pattern = calculate_continuation_logic("وتد هابط", "شراء", current_price, p2, t3)
            elif p3 > p2 > p1 and t3 > t2 > t1:
                if current_price < t3:
                    detected_pattern = calculate_continuation_logic("وتد صاعد", "بيع", current_price, p3, t2)

    # 4. الدمج والتأكيدات النهائية
    if detected_pattern.get("name", "لا يوجد") != "لا يوجد":
        final_output.update({k: v for k, v in detected_pattern.items() if k in final_output or k in ["name", "class", "breakout", "target", "sl"]})
        
        breakout_price = final_output["breakout"]
        is_buy_setup = final_output["target"] > breakout_price
        
        if is_buy_setup and closes[current_candle_idx] > breakout_price:
            final_output["is_body_close"] = 1
        elif not is_buy_setup and closes[current_candle_idx] < breakout_price:
            final_output["is_body_close"] = 1
            
        final_output["is_marubozu_breakout"] = calculate_marubozu_status(
            opens[current_candle_idx], highs[current_candle_idx], lows[current_candle_idx], closes[current_candle_idx]
        )
        
        if "pattern_high" in detected_pattern and "pattern_low" in detected_pattern:
            p_height = detected_pattern["pattern_high"] - detected_pattern["pattern_low"]
            if p_height > 0:
                ret = (detected_pattern["pattern_high"] - current_price) / p_height if is_buy_setup else (current_price - detected_pattern["pattern_low"]) / p_height
                final_output["pattern_retracement_pct"] = round(max(0, ret) * 100, 2)

    return final_output
def calculate_mfi(highs, lows, closes, volumes, period=14):
    """مؤشر تدفق الأموال (MFI): يقيس ضغط الشراء/البيع بدمج السعر مع الحجم"""
    if len(closes) < period + 1: return 50.0
    typical_price = (np.array(highs) + np.array(lows) + np.array(closes)) / 3
    raw_money_flow = typical_price * np.array(volumes)
    
    pos_flow, neg_flow = [], []
    for i in range(1, len(typical_price)):
        if typical_price[i] > typical_price[i-1]:
            pos_flow.append(raw_money_flow[i])
            neg_flow.append(0.0)
        else:
            pos_flow.append(0.0)
            neg_flow.append(raw_money_flow[i])
            
    pos_sum = sum(pos_flow[-period:])
    neg_sum = sum(neg_flow[-period:])
    
    if neg_sum == 0: return 100.0
    mfi = 100 - (100 / (1 + (pos_sum / neg_sum)))
    return round(mfi, 2)

def calculate_cmf(highs, lows, closes, volumes, period=20):
    """مؤشر تشايكين (CMF): يكشف تجميع الحيتان (فوق 0) أو تصريفهم (تحت 0)"""
    if len(closes) < period: return 0.0
    h, l, c, v = np.array(highs), np.array(lows), np.array(closes), np.array(volumes)
    
    divisor = h - l
    # حماية من القسمة على صفر
    divisor = np.where(divisor == 0, 0.0001, divisor)
    mfm = ((c - l) - (h - c)) / divisor
    mfv = mfm * v
    
    cmf = sum(mfv[-period:]) / sum(v[-period:]) if sum(v[-period:]) > 0 else 0.0
    return round(cmf, 4)

def calculate_vwap_and_distance(highs, lows, closes, volumes, current_price):
    """حساب VWAP المرجح بالحجم ومسافة السعر عنه"""
    if len(closes) == 0 or sum(volumes) == 0: return 0.0, 0.0
    typical_price = (np.array(highs) + np.array(lows) + np.array(closes)) / 3
    vwap = np.sum(typical_price * np.array(volumes)) / np.sum(volumes)
    distance_pct = ((current_price - vwap) / vwap) * 100 if vwap > 0 else 0.0
    return round(vwap, 5), round(distance_pct, 2)

def calculate_volume_profile(closes, volumes, bins=20):
    """رسم مبسط لبروفايل الحجم (POC, VAH, VAL)"""
    if len(closes) < bins: return 0.0, 0.0, 0.0
    
    df_vp = pd.DataFrame({'close': closes, 'volume': volumes})
    # تقسيم الأسعار إلى مستويات (Bins)
    df_vp['price_bin'] = pd.cut(df_vp['close'], bins=bins)
    vp = df_vp.groupby('price_bin')['volume'].sum().reset_index()
    
    # نقطة التحكم (أعلى فوليوم)
    poc_idx = vp['volume'].idxmax()
    poc_price = vp.iloc[poc_idx]['price_bin'].mid
    
    # حساب منطقة القيمة (70% من الفوليوم) بشكل مبسط (Upper & Lower)
    total_vol = vp['volume'].sum()
    vah_price = vp['price_bin'].apply(lambda x: x.right).quantile(0.85) # تقدير تقريبي
    val_price = vp['price_bin'].apply(lambda x: x.left).quantile(0.15)  # تقدير تقريبي
    
    return round(poc_price, 5), round(vah_price, 5), round(val_price, 5)
    
def calculate_stochastic(highs, lows, closes, period=14, smooth_k=3):
    """الاستوكاستيك (Stochastic K & D)"""
    if len(closes) < period + smooth_k: return 50.0, 50.0
    h, l, c = np.array(highs), np.array(lows), np.array(closes)
    
    highest_high = pd.Series(h).rolling(window=period).max()
    lowest_low = pd.Series(l).rolling(window=period).min()
    
    k_raw = 100 * ((pd.Series(c) - lowest_low) / (highest_high - lowest_low))
    k_raw = k_raw.fillna(50)
    
    stoch_k = k_raw.rolling(window=smooth_k).mean().iloc[-1]
    stoch_d = k_raw.rolling(window=smooth_k).mean().rolling(window=3).mean().iloc[-1]
    return round(stoch_k, 2), round(stoch_d, 2)

def calculate_williams_r(highs, lows, closes, period=14):
    """ويليامز %R (متخصص في اصطياد القمم والقيعان السريعة)"""
    if len(closes) < period: return -50.0
    highest_high = max(highs[-period:])
    lowest_low = min(lows[-period:])
    if highest_high == lowest_low: return -50.0
    w_r = -100 * ((highest_high - closes[-1]) / (highest_high - lowest_low))
    return round(w_r, 2)

def calculate_choppiness_index(highs, lows, closes, period=14):
    """مؤشر التذبذب المزعج: فوق 61 = تذبذب قاتل، تحت 38 = ترند قوي"""
    if len(closes) < period + 1: return 50.0
    tr_sum = sum([max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(len(closes)-period, len(closes))])
    highest_high = max(highs[-period:])
    lowest_low = min(lows[-period:])
    
    if highest_high - lowest_low == 0: return 50.0
    chop = 100 * np.log10(tr_sum / (highest_high - lowest_low)) / np.log10(period)
    return round(chop, 2)
    
def calculate_ichimoku(highs, lows):
    """سحابة إيشيموكو (Ichimoku Cloud) الأساسية"""
    if len(highs) < 52: return None, None, None, None
    h, l = np.array(highs), np.array(lows)
    
    tenkan = (max(h[-9:]) + min(l[-9:])) / 2
    kijun = (max(h[-26:]) + min(l[-26:])) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (max(h[-52:]) + min(l[-52:])) / 2
    
    return round(tenkan, 5), round(kijun, 5), round(senkou_a, 5), round(senkou_b, 5)

def calculate_supertrend_psar(df, period=10, multiplier=3):
    """دالة مدمجة مبسطة تحاكي قوة السوبر ترند"""
    if len(df) < period + 1: return 0.0, 0.0
    # سوبر ترند تقريبي باستخدام الـ ATR
    atr = calculate_atr(df['high'].values, df['low'].values, df['close'].values, period)
    hl2 = (df['high'].iloc[-1] + df['low'].iloc[-1]) / 2
    supertrend_val = hl2 - (multiplier * atr) if df['close'].iloc[-1] > df['close'].iloc[-2] else hl2 + (multiplier * atr)
    
    # البارابوليك سار (نأخذ أدنى نقطة حديثة كقيمة تقريبية للسار في الترند الصاعد)
    psar_val = df['low'].rolling(5).min().iloc[-2] if df['close'].iloc[-1] > df['close'].iloc[-2] else df['high'].rolling(5).max().iloc[-2]
    
    return round(supertrend_val, 5), round(psar_val, 5)
    
def calculate_pivot_points(high_prev, low_prev, close_prev):
    """النقاط المحورية القياسية بناءً على الشمعة السابقة (اليومية عادة)"""
    p = (high_prev + low_prev + close_prev) / 3
    r1 = (2 * p) - low_prev
    s1 = (2 * p) - high_prev
    return round(p, 5), round(r1, 5), round(s1, 5)

def get_last_fractals(highs, lows):
    """آخر قمة وقاع فركتال (Fractal)"""
    if len(highs) < 5: return 0.0, 0.0
    last_high_fractal = 0.0
    last_low_fractal = 0.0
    
    # البحث من النهاية للبداية عن آخر تشكيل فركتال
    for i in range(len(highs)-3, 1, -1):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            last_high_fractal = highs[i]
            break
            
    for i in range(len(lows)-3, 1, -1):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            last_low_fractal = lows[i]
            break
            
    return round(last_high_fractal, 5), round(last_low_fractal, 5)

def calculate_linreg_curve(closes, period=20):
    """خط الانحدار الخطي لنهاية السعر (مغناطيس الترند)"""
    if len(closes) < period: return closes[-1]
    y = np.array(closes[-period:])
    x = np.arange(len(y))
    slope, intercept, _, _, _ = linregress(x, y)
    linreg_val = (slope * (len(y) - 1)) + intercept
    return round(linreg_val, 5)
    

def extract_symbol_dna(symbol_name: str) -> dict:
    """
    مستخرج البصمة اللفظية (السلاسل والنغمات)
    """
    clean_name = symbol_name.replace("USDT", "").replace("USDC", "")
    length = len(clean_name)
    
    return {
        "length": length,
        "type": "Even" if length % 2 == 0 else "Odd", # السلسلة الفردية والزوجية
        "prefix": clean_name[:2] if length >= 2 else clean_name, # البادئات الوظيفية
        "suffix": clean_name[-2:] if length >= 2 else clean_name, # النهايات المتطابقة
        "first_letter": clean_name[0] if length > 0 else "",
        "last_letter": clean_name[-1] if length > 0 else "",
        "anagram_pool": "".join(sorted(list(clean_name))), # كاشف تبديل المواقع (الحروف مرتبة)
        "core_letters": list(set(clean_name)) # الحروف الصافية لاستخراج العائلة الصوتية
    }


def get_trading_session(timestamp_ms):
    try:
        # بما أنك استوردت datetime مباشرة، نستخدمها هكذا:
        ts = timestamp_ms / 1000
        
        # استخدام utcfromtimestamp لأنه أبسط ويتوافق مع استيرادك
        dt_object = datetime.utcfromtimestamp(ts)
        
        hour = dt_object.hour
        day = dt_object.strftime('%A')
        
        if 0 <= hour < 8:
            session = "Asian (Tokyo/Sydney)"
        elif 8 <= hour < 16:
            session = "European (London)"
        else:
            session = "American (New York)"
            
        return session, day
    except Exception as e:
        logging.error(f"❌ خطأ في دالة الزمن: {e}")
        return "Unknown Session", "Unknown Day"

def clean_nans(d):
    """دالة الفلترة القصوى: تنظف الـ NaN وتسحق أي كائن بانداز/نمباي ليقبله سوبابيس"""
    cleaned = {}
    for k, v in d.items():
        # 1. إذا كان الكائن Series من بانداز، نأخذ القيمة الأخيرة ونحولها لرقم عادي
        if isinstance(v, pd.Series):
            val = v.iloc[-1] if not v.empty else 0.0
            cleaned[k] = float(val) if pd.notna(val) else None
            
        # 2. إذا كان الكائن من أنواع Numpy (مثل np.float64 أو np.int64)
        elif isinstance(v, (np.floating, np.integer)):
            val = float(v) if isinstance(v, np.floating) else int(v)
            cleaned[k] = None if math.isnan(val) else val
            
        # 3. إذا كان رقم بايثون عادي وفيه NaN
        elif isinstance(v, float):
            cleaned[k] = None if math.isnan(v) else v
            
        # 4. إذا كان قاموس (نطبق الدالة عليه بشكل متداخل)
        elif isinstance(v, dict):
            cleaned[k] = clean_nans(v)
            
        # 5. إذا كانت قائمة (نتأكد من تنظيف محتواها)
        elif isinstance(v, list):
            cleaned_list = []
            for item in v:
                if isinstance(item, (np.floating, np.integer)):
                    cleaned_list.append(float(item) if isinstance(item, np.floating) else int(item))
                else:
                    cleaned_list.append(item)
            cleaned[k] = cleaned_list
            
        # أي نوع آخر (نصوص، بوليان) يمر بسلام
        else:
            cleaned[k] = v
            
    return cleaned

async def update_live_status(symbol, current_price, current_change):
    try:
        response = supabase.table("forensic_reports") \
            .select("id") \
            .eq("symbol", symbol) \
            .order("trigger_candle_timestamp_ms", desc=True) \
            .limit(1) \
            .execute()

        if response.data:
            record_id = response.data[0]['id']
            supabase.table("forensic_reports") \
                .update({
                    "price_after_event": float(current_price),
                    "price_change_percent_final": float(current_change)
                }) \
                .eq("id", record_id) \
                .execute()
    except Exception as e:
        logging.error(f"⚠️ فشل تحديث مسار {symbol}: {str(e)}")


import json

async def async_manual_upsert1(table_name, records, retry_count=0, max_retries=3):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    endpoint = f"{SUPABASE_URL}/rest/v1/{table_name}"
    
    # ⏱️ وضع حد زمني ذكي
    timeout = aiohttp.ClientTimeout(total=45, connect=15)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint, json=records, headers=headers) as response:
                if response.status in [200, 201, 204]:
                    return True
                else:
                    error_text = await response.text()
                    
                    # 1. [ نظام الشفاء الذاتي للمحقق كونان (الأعمدة المفقودة) ]
                    try:
                        error_json = json.loads(error_text)
                        if error_json.get("code") == "PGRST204" and retry_count < 1:
                            match = re.search(r"Could not find the '(.*?)' column", error_json.get("message", ""))
                            if match:
                                missing_col = match.group(1)
                                logging.warning(f"🔍 اكتشاف خلل: العمود المفقود ({missing_col}). جاري البناء التلقائي...")
                                
                                rpc_endpoint = f"{SUPABASE_URL}/rest/v1/rpc/add_dynamic_column"
                                async with session.post(rpc_endpoint, json={"p_table_name": table_name, "p_column_name": missing_col}, headers=headers) as rpc_response:
                                    if rpc_response.status in [200, 204]:
                                        logging.info("✅ تم ترميم الجدول. يتم تحديث الذاكرة...")
                                        await asyncio.sleep(2) 
                                        return await async_manual_upsert1(table_name, records, retry_count=retry_count + 1, max_retries=max_retries)
                    except json.JSONDecodeError:
                        pass
                    
                    # 2. [ نظام التقاط الأنفاس (الخادم مشغول أو طلبات كثيرة) ]
                    if response.status in [429, 500, 502, 503, 504] and retry_count < max_retries:
                        wait_time = 3 * (retry_count + 1) # الانتظار يطول مع كل محاولة (3 ثوان، ثم 6، ثم 9)
                        logging.warning(f"⏳ الخادم مضغوط (الحالة {response.status}). المحقق يأخذ نفساً لمدة {wait_time} ثوانٍ ثم يعاود...")
                        await asyncio.sleep(wait_time)
                        return await async_manual_upsert1(table_name, records, retry_count=retry_count + 1, max_retries=max_retries)

                    # إذا كان الخطأ مختلفاً ولا يمكن علاجه
                    logging.error(f"❌ فشل الرفع إلى {table_name}! الحالة: {response.status}")
                    logging.error(f"📝 رسالة الخطأ: {error_text}")
                    return False
                    
    except asyncio.TimeoutError:
        # 3. [ نظام التقاط الأنفاس عند نفاد الوقت Timeout ]
        if retry_count < max_retries:
            wait_time = 3 * (retry_count + 1)
            logging.warning(f"⏳ نفد الوقت لجدول {table_name}. نأخذ نفساً عميقاً ({wait_time}ث) ثم نحاول (محاولة {retry_count+1}/{max_retries})...")
            await asyncio.sleep(wait_time)
            return await async_manual_upsert1(table_name, records, retry_count=retry_count + 1, max_retries=max_retries)
        else:
            logging.error(f"❌ استسلام: نفد الوقت تماماً أثناء الرفع لجدول {table_name} بعد {max_retries} محاولات.")
            return False
            
    except Exception as e:
        logging.error(f"⚠️ خطأ تقني أثناء محاولة الرفع إلى {table_name}: {str(e)}")
        return False

async def fetch_klines1(session, symbol, interval, limit=350): # تم رفع الحد إلى 300 لحساب EMA 200 بأمان
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        async with session.get(url, timeout=10) as res:
            if res.status == 200: 
                return await res.json()
    except Exception as e:
        logging.error(f"❌ خطأ في جلب بيانات {symbol} فريم {interval}: {e}")
    return None
    
async def safe_ai_handover(report_id, symbol):
    """غلاف حماية يضمن عدم موت الذكاء الاصطناعي بصمت"""
    try:
        await analyze_trend_structure_with_ai(report_id, symbol)
        logging.info(f"🧠 [الذكاء الاصطناعي] أتم تحليل {symbol} بنجاح.")
    except Exception as e:
        logging.error(f"❌ [انهيار الذكاء الاصطناعي] فشل تحليل {symbol}: {e}")
        
async def run_forensic_autopsy(symbol, change_percent, explosion_time_ms):
    """
    🕵️‍♂️ وحدة التحقيق الجنائي المتقدمة (المحقق كونان v3.1 - إصدار أثير للتحليل العميق)
    """
    try:
        # --- 🚀 إضافة "موزع الجهد" لتفريق الاختناق المروري ---
        import random
        await asyncio.sleep(random.uniform(0.1, 2.0)) # تأخير عشوائي بين 0.1 و 2 ثانية
        # --------------------------------------------------

        # 🛡️ فلتر الأمان: التأكد من أن العملة ضمن نطاق التحقيق المطلوب
        # 💡 تم التعديل إلى 60 للصعود، و -70 للهبوط (بالسالب)
        if change_percent >= 30:
            event_type = "PUMP"
        elif change_percent <= -70:
            event_type = "DUMP"
        else:
            return  # تجاهل إذا لم تكن مطابقة للشروط

        # ⚠️ أضفنا وقت الجريمة بالملي ثانية في رسالة الطباعة لتوثيق اللحظة بدقة
        print(f"\n🕵️‍♂️ [المحقق كونان] فتح ملف تحقيق شامل للعملة {symbol} | الحدث: {event_type} ({change_percent}%) | وقت الانفجار: {explosion_time_ms} ms")
        
        timeframes = ['1h', '2h', '4h', '1d']
        klines_data = {}
        
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_klines1(session, symbol, tf, limit=300) for tf in timeframes]
            results = await asyncio.gather(*tasks)
            
            for i, tf in enumerate(timeframes):
                if results[i]: klines_data[tf] = results[i]
                
        if '1h' not in klines_data or len(klines_data['1h']) < 50:
            print(f"⚠️ [المحقق كونان] الأدلة غير كافية لعملة {symbol}. إغلاق الملف.")
            return

        # ... (باقي كود التحليل الخاص بك) ...
        # ==========================================
        # 🕵️‍♂️ 1. تحديد "ساعة الصفر" من فريم الساعة (1H)
        # ==========================================
        df_1h = pd.DataFrame(klines_data['1h'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume', 'taker_base_vol', 'timestamp']:
            df_1h[col] = df_1h[col].astype(float)
            
        df_1h['body_size'] = abs(df_1h['close'] - df_1h['open']) / df_1h['open'] * 100
        point_zero_idx = df_1h['body_size'].idxmax()
        
        if point_zero_idx < 25:
            print(f"⚠️ [المحقق كونان] الحدث حصل مبكراً جداً ولا يوجد تاريخ كافي لما قبل الكارثة. {symbol}")
            return

        point_zero_timestamp = int(df_1h.iloc[point_zero_idx]['timestamp'])
        current_timestamp = int(df_1h.iloc[-1]['timestamp'])

        # ==========================================
        # 🦈 [ إضافة بصمات الحيتان والأموال الذكية ]
        # ==========================================
        
        # 1. حساب صافي سيولة الحيتان (Whale Net Flow)
        tbv_before = float(df_1h.iloc[point_zero_idx - 1]['taker_base_vol']) # شراء السوق
        total_vol_before = float(df_1h.iloc[point_zero_idx - 1]['volume'])
        tsv_before = total_vol_before - tbv_before # بيع السوق
        taker_buy_ratio = (tbv_before / tsv_before) if tsv_before > 0 else 1.0
        whale_net_flow = tbv_before - tsv_before # 👈 الدليل القاطع على اتجاه السيولة
        
        # 2. كاشف الفجوات العادلة (FVG Size) قبل الانفجار
        fvg_size_pct = 0.0
        if point_zero_idx >= 2:
            c1_high = float(df_1h.iloc[point_zero_idx - 2]['high'])
            c1_low = float(df_1h.iloc[point_zero_idx - 2]['low'])
            c3_high = float(df_1h.iloc[point_zero_idx]['high'])
            c3_low = float(df_1h.iloc[point_zero_idx]['low'])
            
            if c1_high < c3_low:  # Bullish FVG
                fvg_size_pct = ((c3_low - c1_high) / c1_high) * 100
            elif c1_low > c3_high: # Bearish FVG
                fvg_size_pct = ((c1_low - c3_high) / c3_high) * 100

        # ==========================================
        # 🕯️ 2. دالة كشف أنماط الشموع ما قبل الكارثة
        # ==========================================
        def extract_past_patterns(tf_data):
            past_data = [k for k in tf_data if int(k[0]) < point_zero_timestamp]
            if len(past_data) < 25: return "No Pattern"
            
            df_past = pd.DataFrame(past_data[-25:], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tbv', 'tqv', 'ig'])
            for col in ['open', 'high', 'low', 'close']:
                df_past[col] = df_past[col].astype(float)
                
            try:
                detected = detect_all_pdf_patterns(df_past)
                if isinstance(detected, list):
                    valid_patterns = [p for p in detected if p and isinstance(p, str)]
                    return ", ".join(set(valid_patterns)) if valid_patterns else "Normal"
                elif isinstance(detected, str) and detected.strip():
                    return detected
                return "Normal"
            except Exception as e:
                print(f"⚠️ [المحقق كونان] خطأ أثناء فحص الشموع: {e}")
                return "Neutral"
                  
        patterns_1h = extract_past_patterns(klines_data.get('1h', []))
        patterns_2h = extract_past_patterns(klines_data.get('2h', []))
        patterns_4h = extract_past_patterns(klines_data.get('4h', []))
        patterns_1d = extract_past_patterns(klines_data.get('1d', []))

        # ==========================================
        # 🌟 استخراج بيانات 4h لتمريرها لمحرك النماذج والدايفرجنس
        # ==========================================
        past_data_4h = [k for k in klines_data.get('4h', []) if int(k[0]) < point_zero_timestamp]
        df_4h_past = None
        if len(past_data_4h) >= 25:
            df_4h_past = pd.DataFrame(past_data_4h, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
            ])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df_4h_past[col] = df_4h_past[col].astype(float)

        # ==========================================
        # 🧬 3. دالة تشريح الفريمات (محدثة بالمحركات الجديدة)
        # ==========================================
        def dissect_timeframe(tf_data, tf_name, df_4h_ref=None):
            past_data = [k for k in tf_data if int(k[0]) < point_zero_timestamp]
            if len(past_data) < 25: return None
            
            # تحويل البيانات إلى DataFrame لمحركات التحليل
            df_past = pd.DataFrame(past_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                'ct', 'qav', 'nt', 'tbv', 'tqv', 'ig'
            ])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df_past[col] = df_past[col].astype(float)
                
            highs = df_past['high'].tolist()
            lows = df_past['low'].tolist()
            closes = df_past['close'].tolist()
            volumes = df_past['volume'].tolist()
            
            # --- حسابات المؤشرات الأساسية ---
            upper, mid, lower = calculate_bollinger(closes) if len(closes) >= 20 else (None, None, None)
            bbw_val = (upper - lower) / mid if (mid and mid > 0) else 0
            kc_up, kc_mid, kc_low = calculate_keltner_channels(highs, lows, closes) if len(closes) >= 20 else (None, None, None)
            obv_val = calculate_obv(closes, volumes)
            obv_prev_val = calculate_obv(closes[:-1], volumes[:-1]) if len(closes) > 1 else 0.0
            # --- تشغيل المحركات الجديدة ---
            macd_data = calculate_macd_values(closes)
            trend_info, s_highs, s_lows = generate_trend_data(df_past)
            channel_info = calculate_price_channel(df_past, trend_info, s_highs, s_lows)
            pattern_data = detect_patterns_and_calculate(df_past, symbol, tf_name, df_4h=df_4h_ref)
            
            # 👈 [ ضع المحركات الجديدة هنا ] 👉
            mfi_val = calculate_mfi(highs, lows, closes, volumes, 14)
            cmf_val = calculate_cmf(highs, lows, closes, volumes, 20)
            vwap_val, vwap_dist = calculate_vwap_and_distance(highs, lows, closes, volumes, closes[-1])
            poc_val, vah_val, val_val = calculate_volume_profile(closes, volumes)
            
            stoch_k, stoch_d = calculate_stochastic(highs, lows, closes)
            will_r = calculate_williams_r(highs, lows, closes)
            chop_index = calculate_choppiness_index(highs, lows, closes)
            
            tenkan, kijun, senkou_a, senkou_b = calculate_ichimoku(highs, lows)
            supertrend, psar = calculate_supertrend_psar(df_past)
            frac_high, frac_low = get_last_fractals(highs, lows)
            linreg = calculate_linreg_curve(closes)
            
            report = {
                f"ema_20_{tf_name}": float(calculate_ema(closes, 20)) if len(closes) >= 20 else None,
                f"ema_50_{tf_name}": float(calculate_ema(closes, 50)) if len(closes) >= 50 else None,
                f"ema_100_{tf_name}": float(calculate_ema(closes, 100)) if len(closes) >= 100 else None,
                f"ema_200_{tf_name}": float(calculate_ema(closes, 200)) if len(closes) >= 200 else None,
                f"rsi_{tf_name}": calculate_rsi(closes) if len(closes) >= 14 else None,
                # احذف السطر المكرر الخاص بـ rsi_tf_name الذي يحتوي على iloc
                f"obv_{tf_name}": float(obv_val) if obv_val else None,
                f"obv_slope_{tf_name}": float(obv_val - obv_prev_val) if obv_val else None,
                f"adx_{tf_name}": float(calculate_adx(highs, lows, closes)) if len(closes) >= 14 else None,
                f"bb_upper_{tf_name}": float(upper) if upper else None,
                f"bb_middle_{tf_name}": float(mid) if mid else None,
                f"bb_lower_{tf_name}": float(lower) if lower else None,
                f"atr_{tf_name}": calculate_atr(highs, lows, closes) if len(closes) >= 14 else None,
                f"was_squeezed_{tf_name}": bool(bbw_val < 0.07) if bbw_val else None,
                f"kc_upper_{tf_name}": kc_up,
                f"kc_middle_{tf_name}": kc_mid,
                f"kc_lower_{tf_name}": kc_low,
                f"bbw_{tf_name}": bbw_val,
                # إعدادات الحجم الأساسية
                "last_volume": volumes[-1],
                "avg_volume_20": sum(volumes[-20:]) / 20 if len(volumes) >= 20 else (sum(volumes)/len(volumes) if volumes else 0),
                "last_close": closes[-1],
                
                # --- بصمات الماكد ---
                f"macd_{tf_name}": macd_data.get('macd'),
                f"macd_signal_{tf_name}": macd_data.get('signal'),
                f"macd_hist_{tf_name}": macd_data.get('hist'),
                
                # --- بصمات الترند ---
                f"{tf_name}_trend_direction": trend_info.get("direction", "عرضي"),
                f"{tf_name}_trend_slope_angle": float(trend_info.get("angle", 0.0)),
                f"{tf_name}_trend_touches": int(trend_info.get("touches", 0)),
                f"{tf_name}_trend_current_price": float(trend_info.get("current_line_price", 0.0)),
                f"{tf_name}_is_valid_trend": int(trend_info.get("is_valid", 2)),
                
                # --- بصمات القنوات السعرية ---
                f"{tf_name}_channel_upper": float(channel_info.get("channel_upper", 0.0)),
                f"{tf_name}_channel_lower": float(channel_info.get("channel_lower", 0.0)),
                f"{tf_name}_channel_direction": channel_info.get("channel_direction", "NONE"),
                f"{tf_name}_channel_touches": int(channel_info.get("channel_touches", 0)),
                f"{tf_name}_channel_status": channel_info.get("channel_status", "NONE"),
                
                # --- بصمات النماذج ---
                f"{tf_name}_pattern_name": pattern_data.get("name", "NONE"),
                f"{tf_name}_pattern_class": pattern_data.get("class", "NONE"),
                f"{tf_name}_pattern_breakout": float(pattern_data.get("breakout", 0.0)),
                f"{tf_name}_pattern_target": float(pattern_data.get("target", 0.0)),
                f"{tf_name}_pattern_sl": float(pattern_data.get("sl", 0.0)),

                f"mfi_{tf_name}": mfi_val,
                f"cmf_{tf_name}": cmf_val,
                f"vwap_{tf_name}": vwap_val,
                f"vwap_distance_pct_{tf_name}": vwap_dist,
                f"poc_price_{tf_name}": float(poc_val) if poc_val else None,
                f"value_area_high_{tf_name}": float(vah_val) if vah_val else None,
                f"value_area_low_{tf_name}": float(val_val) if val_val else None,
                f"volume_oscillator_{tf_name}": float(vol_osc_val) if 'vol_osc_val' in locals() and vol_osc_val else None, # تأكد أنك تحسب vol_osc_val في المحركات فوق

                f"stochastic_k_{tf_name}": stoch_k,
                f"stochastic_d_{tf_name}": stoch_d,
                f"williams_r_{tf_name}": will_r,
                f"choppiness_index_{tf_name}": chop_index,
                
                f"ichimoku_conversion_{tf_name}": tenkan,
                f"ichimoku_base_{tf_name}": kijun,
                f"ichimoku_cloud_top_{tf_name}": senkou_a,
                f"ichimoku_cloud_bottom_{tf_name}": senkou_b,
                f"supertrend_{tf_name}": supertrend,
                f"parabolic_sar_{tf_name}": psar,
                
                f"last_fractal_high_{tf_name}": frac_high,
                f"last_fractal_low_{tf_name}": frac_low,
                f"lin_reg_curve_{tf_name}": linreg,
            }
            
            # --- حقن الأعمدة الخاصة بـ فريم الساعة (1h) كمرجع رئيسي ---
            if tf_name == '1h':
                report.update({
                    "is_body_close": int(pattern_data.get("is_body_close", 2)),
                    "channel_weakness": pattern_data.get("channel_weakness", "NONE"),
                    "pattern_retracement_pct": float(pattern_data.get("pattern_retracement_pct", 0.0)),
                    "pattern_apex_progress": float(pattern_data.get("pattern_apex_progress", 0.0)),
                    "is_marubozu_breakout": int(pattern_data.get("is_marubozu_breakout", 2)),
                    "rsi_divergence_4h": pattern_data.get("rsi_divergence_4h", "NONE"),
                    "harmonic_fib_accuracy": float(pattern_data.get("harmonic_fib_accuracy", 0.0)),
                    "harmonic_d_confluence": int(pattern_data.get("harmonic_d_confluence", 2)),
                    "1h_trend_angle": float(pattern_data.get("1h_trend_angle", 0.0))
                })
                
            return report

        # تنفيذ التشريح
        report_1h = dissect_timeframe(klines_data.get('1h', []), '1h', df_4h_past)
        report_2h = dissect_timeframe(klines_data.get('2h', []), '2h', df_4h_past)
        report_4h = dissect_timeframe(klines_data.get('4h', []), '4h', df_4h_past)
        report_1d = dissect_timeframe(klines_data.get('1d', []), '1d', df_4h_past)

        if not report_1h: 
            return

        # 🧮 حسابات الحركة السعرية والانحرافات
        price_before = float(report_1h['last_close'])
        price_after = float(df_1h.iloc[-1]['close'])
        actual_change_percent = ((price_after - price_before) / price_before) * 100
        duration_mins = int((current_timestamp - point_zero_timestamp) / 60000)
        vol_spike_ratio = report_1h['last_volume'] / report_1h['avg_volume_20'] if report_1h.get('avg_volume_20', 0) > 0 else 1

        closes_1h = df_1h['close'].iloc[:point_zero_idx].tolist()
        rsi_1h_vals = [float(calculate_rsi(closes_1h[:i+1]).iloc[-1]) for i in range(max(0, len(closes_1h)-10), len(closes_1h))]
        obv_1h_vals = [calculate_obv(closes_1h[:i+1], df_1h['volume'].iloc[:i+1].tolist()) for i in range(max(0, len(closes_1h)-10), len(closes_1h))]
        
        rsi_div = detect_divergence(closes_1h[-10:], [r for r in rsi_1h_vals if r is not None])
        obv_div = detect_divergence(closes_1h[-10:], [o for o in obv_1h_vals if o is not None])

        session, day_of_week = get_trading_session(point_zero_timestamp)

        # تجهيز البصمة الوراثية قبل دمجها
        symbol_dna = extract_symbol_dna(symbol)
        
        # تحديد دور العملة بناءً على نسبة التغير
        if actual_change_percent >=20:
            c_role = "LEADER"
        elif actual_change_percent <= -10:
            c_role = "BLEEDER"
        elif 1 <= actual_change_percent <= 5:
            c_role = "INFILTRATOR"
        else:
            c_role = "FOLLOWER"

        # ==========================================
        # 📑 4. إنشاء المفتاح الموحد وتوزيع البيانات على 4 جداول
        # ==========================================
        # إنشاء report_id موحد لربط جميع الجداول (مثال: BTCUSDT_1715480000)
        report_id = f"{symbol}_{int(point_zero_timestamp)}"

        # 1️⃣ [ الجدول الرئيسي: liquidity_ratios ]
        raw_liquidity = {
            "report_id": report_id,
            "symbol": symbol,
            "event_type": event_type,
            "trigger_candle_timestamp_ms": int(point_zero_timestamp),
            "price_before_event": price_before,
            "price_after_event": price_after,
            "price_change_percent": float(change_percent),
            "price_change_percent_final": float(actual_change_percent),
            "event_duration_minutes": duration_mins,
            "volume_before_event": float(report_1h['last_volume']),
            "volume_spike_ratio": float(vol_spike_ratio),
            "whale_net_flow_volume": float(whale_net_flow),
            "taker_buy_ratio_1h": float(taker_buy_ratio),
            "fvg_gap_size": float(fvg_size_pct),
            "trading_session": session,
            "day_of_week": day_of_week,
            "dna_json": symbol_dna,
            "cluster_role": c_role,
            "cluster_power": float(vol_spike_ratio * actual_change_percent),
            "lost_cluster_liquidity": "UNKNOWN",
            "rotation_status": "ACCUMULATION" if c_role == "INFILTRATOR" else "DISTRIBUTION",
            "similarity_score": 0,
            "infiltrator_targets": [],
            "metadata": {"version": "Conan_v3.2_Cluster_Edition"}
        }

        # 2️⃣ [ جدول الشموع والنماذج: candlesticks_and_patterns ]
        raw_candlesticks = {
            "report_id": report_id,
            "symbol": symbol,
            "event_type": event_type,
            "patterns_1h": patterns_1h,
            "patterns_2h": patterns_2h,
            "patterns_4h": patterns_4h,
            "patterns_1d": patterns_1d,
            "is_body_close": report_1h.get("is_body_close", 2),
            "pattern_retracement_pct": report_1h.get("pattern_retracement_pct", 0.0),
            "pattern_apex_progress": report_1h.get("pattern_apex_progress", 0.0),
            "is_marubozu_breakout": report_1h.get("is_marubozu_breakout", 2),
            "harmonic_fib_accuracy": report_1h.get("harmonic_fib_accuracy", 0.0),
            "harmonic_d_confluence": report_1h.get("harmonic_d_confluence", 2),
            "channel_weakness": report_1h.get("channel_weakness", "NONE"),
            "1h_trend_angle": report_1h.get("1h_trend_angle", 0.0)
        }
        
        # 3️⃣ [ جدول الزخم: momentum_indicators ]
        raw_momentum = {
            "report_id": report_id,
            "symbol": symbol,
            "event_type": event_type,
            "rsi_divergence_1h": rsi_div,
            "rsi_divergence_4h": report_1h.get("rsi_divergence_4h", "NONE"),
            "obv_divergence_1h": obv_div,
        }

        # 4️⃣ [ جدول المتوسطات: moving_averages_and_bands ]
        raw_ma_bands = {
            "report_id": report_id,
            "symbol": symbol,
            "event_type": event_type,
            "is_above_ema_200_1d": bool(report_1d['last_close'] > report_1d['ema_200_1d']) if report_1d and report_1d.get('ema_200_1d') else None,
        }

        # 5️⃣ 👈 [ أضف جدول السيولة الذكية هنا ] 👉
        raw_smart_money = {
            "report_id": report_id,
            "symbol": symbol,
            "event_type": event_type,
        }

        # تغذية الجداول الفرعية ببيانات الفريمات (1h, 2h, 4h, 1d) ديناميكياً
        for tf, rep in [('1h', report_1h), ('2h', report_2h), ('4h', report_4h), ('1d', report_1d)]:
            if rep:
                raw_candlesticks.update({k: v for k, v in rep.items() if any(x in k for x in ['pattern_', 'trend_', 'channel_', 'fractal_', 'lin_reg', 'pivot', 'support', 'resistance'])})
                raw_momentum.update({k: v for k, v in rep.items() if any(x in k for x in ['rsi_', 'macd_', 'obv_', 'adx_', 'atr_', 'stoch', 'williams', 'choppiness', 'squeeze'])})
                raw_ma_bands.update({k: v for k, v in rep.items() if any(x in k for x in ['ema_', 'bb_', 'kc_', 'was_squeezed', 'bbw_', 'ichimoku', 'supertrend', 'parabolic'])})
                raw_smart_money.update({k: v for k, v in rep.items() if any(x in k for x in ['mfi_', 'cmf_', 'vwap_', 'poc_', 'value_area_', 'volume_oscillator_'])})
        # ==========================================
        # 🛡️ 5. تنظيف الأدلة ورفعها بأمان إلى قواعد البيانات
        # ==========================================
        # تنظيف القيم الفارغة (NaN) قبل الرفع لتجنب أخطاء سوبابيس
        clean_liquidity = clean_nans(raw_liquidity)
        clean_candlesticks = clean_nans(raw_candlesticks)
        clean_momentum = clean_nans(raw_momentum)
        clean_ma_bands = clean_nans(raw_ma_bands)
        clean_smart_money = clean_nans(raw_smart_money) # 👈 1. إضافة تنظيف الجدول الخامس

        # 👈 تعديل النص ليكون "الأدلة الخمسة" بدلاً من الأربعة
        print(f"✅ [المحقق كونان] تم تجهيز الأدلة الخمسة لـ {symbol}. السيولة الصافية: {whale_net_flow:.2f} | الفجوة: {fvg_size_pct:.2f}%")

        # 🚨 خطوة حرجة: يجب رفع الجدول الرئيسي أولاً لتفعيل الـ PRIMARY KEY
        success_main = await async_manual_upsert1("liquidity_ratios", [clean_liquidity])
        
        if success_main:
            # إذا نجح رفع الرئيسي، يمكننا رفع الجداول الفرعية بالتوازي لتوفير الوقت
            upload_tasks = [
                async_manual_upsert1("candlesticks_and_patterns", [clean_candlesticks]),
                async_manual_upsert1("momentum_indicators", [clean_momentum]),
                async_manual_upsert1("moving_averages_and_bands", [clean_ma_bands]),
                async_manual_upsert1("smart_money_and_volume_profile", [clean_smart_money]) # 👈 2. إضافة الجدول للرفع المتوازي
            ]
            
            results = await asyncio.gather(*upload_tasks)
            
            if all(results):
                print(f"🎉 [المحقق كونان] تم إغلاق القضية وأرشفة جميع ملفات {symbol} بالكامل في سوبابيس.")
                # ==========================================
                print(f"🧬 [تسليم الراية] جاري إرسال القضية ({report_id}) لغرفة الذكاء الاصطناعي...")
                # استخدمنا المرجع (task) لحماية المهمة من الموت المفاجئ
                task = asyncio.create_task(safe_ai_handover(report_id, symbol))
                # ==========================================
            else:
                print(f"⚠️ [المحقق كونان] تم رفع الرئيسي، لكن حدث نقص في رفع بعض الأدلة الفرعية لعملة {symbol}.")

    except Exception as e:
        print(f"\n☠️ [المحقق كونان] انهيار أثناء تشريح {symbol}: {str(e)}")
        logging.error(traceback.format_exc())
        

import time
import asyncio
import aiohttp
import logging
# أضفنا =None لجعل المتغير اختيارياً وليس إجبارياً
async def forensic_investigation_cycle(active_investigations=None):
    """
    🕵️‍♂️ دورة المحقق الجنائي: ترصد الانفجارات والانهيارات (طلقة واحدة) وتتكرر كل ساعة تلقائياً.
    """
    # إذا لم يتم تمرير قاموس من الخارج، قم بإنشاء واحد جديد هنا
    if active_investigations is None:
        active_investigations = {}
        
    # إضافة حلقة التكرار اللانهائية لتعمل الدالة بشكل مستمر
    while True:
        logging.info("🕵️‍♂️ [المحقق كونان] بدء جولة التفتيش الجنائي (العقود الآجلة) - جولة جديدة...")
        
        # تحويل الوقت الحالي إلى ملي ثانية (Millisecond)
        current_time_ms = int(time.time() * 1000)
        
        # 1. تنظيف الذاكرة: ننسى العملة بعد 24 ساعة (لكي لا نرصدها مئات المرات في نفس اليوم)
        keys_to_remove = [
            sym for sym, timestamp_ms in active_investigations.items() 
            if current_time_ms - timestamp_ms > 86400000
        ]
        for k in keys_to_remove:
            del active_investigations[k]

        try:
            async with aiohttp.ClientSession() as session:
                # استخدام رابط العقود الآجلة الخاص بـ Binance
                async with session.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=10) as res:
                    if res.status == 200:
                        tickers = await res.json()
                        tasks = []
                        
                        # 2. البحث عن الجرائم الجديدة فقط
                        for coin in tickers:
                            symbol = coin.get('symbol', '')
                            
                            # استبعاد العملات التي ليست USDT، والعملات المستقرة
                            if not symbol.endswith('USDT') or symbol in ['USDCUSDT', 'FDUSDUSDT', 'BUSDUSDT']: 
                                continue
                                
                            # فلتر العملات الموقوفة
                            count = int(coin.get('count', 0))
                            if count == 0:
                                continue
                                
                            change = float(coin.get('priceChangePercent', 0))
                            vol = float(coin.get('quoteVolume', 0))
                            
                            # الحصول على وقت الانفجار
                            close_time_ms = int(coin.get('closeTime', current_time_ms))
                            
                            # هل هي جريمة جديدة؟ (+60% صعود أو -70% هبوط)
                            if vol > 50000 and (change >= 30 or change <= -70):
                                # إذا لم نقم بتشريحها من قبل في هذا اليوم
                                if symbol not in active_investigations:
                                    # نسجلها في القائمة لمنع تكرار التحليل لها اليوم
                                    active_investigations[symbol] = close_time_ms
                                    logging.info(f"🚨 [المحقق] رصد حدث جديد {symbol} بنسبة {change}% في الوقت {close_time_ms} ms")
                                    
                                    # إرسالها للتشريح (مرة واحدة وتنتهي)
                                    tasks.append(run_forensic_autopsy(symbol, change, close_time_ms))
                            
                        # 3. التنفيذ المتوازي للتشريحات الجديدة فقط
                        if tasks:
                            await asyncio.gather(*tasks)
                            
        except Exception as e:
            logging.error(f"⚠️ خطأ في دورة المحقق الجنائي: {e}")
            
        print(f"🏁 [المحقق] أنهى جولته. ذاكرة منع التكرار تحتوي حالياً على {len(active_investigations)} عملة.")
        
        # ⏳ [ الإضافة الجديدة ] التوقف المؤقت لمدة ساعة (3600 ثانية) قبل بدء الجولة القادمة
        logging.info("⏳ [المحقق كونان] في فترة استراحة. الجولة القادمة ستبدأ بعد ساعة من الآن...")
        await asyncio.sleep(3600)
       
# 1. 🟢 ضع هذا الكلاس قبل "نظام الإنعاش الأبدي" (في منطقة عامة خارج الدوال)
class TelegramLoggerHandler(logging.Handler):
    def __init__(self, bot, chat_id, loop):
        super().__init__()
        self.bot = bot
        self.chat_id = chat_id
        self.loop = loop # استقبال الـ Loop الرئيسي

    def emit(self, record):
        log_entry = self.format(record)
        if record.levelno >= logging.ERROR:
            try:
                # توجيه الخطأ للتلجرام بأمان تام
                asyncio.run_coroutine_threadsafe(self.send_log(log_entry), self.loop)
            except Exception as e:
                print(f"⚠️ فشل إرسال اللوج للتليجرام: {e}")

    async def send_log(self, message):
        try:
            msg = f"⚠️ <b>تنبيـه خطأ في النظام:</b>\n<code>{message[:3500]}</code>"
            await self.bot.send_message(self.chat_id, msg, parse_mode="HTML")
        except Exception:
            pass
# ==========================================
# 5. نهاية الملف: نظام الإنعاش الأبدي 24/7 (النبض الذاتي) ⚡
# ==========================================
import os
import asyncio
import logging
import random
import aiohttp
from aiohttp import web

# ==========================================
# 5. نظام الإنعاش الأبدي: "لا تأخذه سنة ولا نوم" ⚡
# ==========================================
async def sync_and_error_bridge():
    """
    الجسر المطور: يفحص الأخطاء، ويرسل الإشعارات، ويتأكد من الدور.
    تمت إضافة نظام معالجة الجلسات المغلقة (Session Fix).
    """
    headers = {
        "apikey": SUPABASE_KEY, 
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        # ✅ فتح جلسة جديدة لكل محاولة لضمان عدم حدوث Session is closed
        async with aiohttp.ClientSession() as session:
            
            # [1] جلب الأخطاء الجديدة من السكربت
            error_url = f"{SUPABASE_URL}/rest/v1/script_errors?is_reported=eq.false"
            async with session.get(error_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    errors = await resp.json()
                    for err in errors:
                        alert = f"⚠️ <b>تنبيه من السكربت الخارجي:</b>\n<code>{err['error_message']}</code>"
                        try:
                            await bot.send_message(GROUP_ID, alert, parse_mode="HTML")
                            # تحديث الحالة إلى "تم التبليغ"
                            update_url = f"{SUPABASE_URL}/rest/v1/script_errors?id=eq.{err['id']}"
                            await session.patch(update_url, json={"is_reported": True}, headers=headers)
                        except Exception as telegram_err:
                            logging.error(f"❌ فشل إرسال تنبيه تلجرام: {telegram_err}")

            # [2] تنظيف الأخطاء القديمة (اختياري لتوفير المساحة)
            delete_url = f"{SUPABASE_URL}/rest/v1/script_errors?is_reported=eq.true"
            await session.delete(delete_url, headers=headers)

            # [3] فحص من عليه الدور الآن؟
            sync_url = f"{SUPABASE_URL}/rest/v1/system_sync?id=eq.1"
            async with session.get(sync_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    sync_data = await resp.json()
                    if sync_data:
                        return sync_data[0]['current_turn']
                else:
                    logging.warning(f"⚠️ فشل جلب الدور من سوبابيس، كود الحالة: {resp.status}")

    except aiohttp.ClientError as e:
        logging.error(f"🌐 خطأ في اتصال الشبكة: {e}")
    except Exception as e:
        logging.error(f"⚠️ خطأ غير متوقع في جسر التنسيق: {e}")
    
    return "wait" # في حالة أي خلل، نطلب من المايسترو الانتظار


async def handle_ping(request):
    """استجابة سريعة لإخبار السيرفر أن النظام مستيقظ"""
    return web.Response(
        text="Alive & Vigilant ⚡", 
        headers={"Connection": "keep-alive"}
    )


async def handle_telegram_login(request):
    return web.Response(text="✅ Data Received")


async def self_resuscitation():
    """النبض الذاتي: البوت يوقظ نفسه لمنع النوم (Anti-Idle)"""
    render_url = os.getenv("RENDER_EXTERNAL_URL") 
    if not render_url: return

    while True:
        try:
            # كسر التخزين المؤقت لضمان وصول الطلب للمعالج مباشرة
            rand_ping = f"{render_url}?v={random.randint(1, 99999)}"
            async with aiohttp.ClientSession() as session:
                async with session.get(rand_ping, timeout=10) as response:
                    logging.info(f"💉 [نبضة حية]: {response.status}")
        except Exception as e:
            logging.error(f"⚠️ [فشل النبض]: {e}")
        
        await asyncio.sleep(240) # كل 4 دقائق


async def watch_dog(task_func, *args):
    """
    بروتوكول اليقظة: مراقب دائم للمحركات.
    إذا توقف أي محرك (سنة) أو انهار (نوم)، يعيده للحياة فوراً.
    """
    while True:
        try:
            logging.info(f"🛡️ تشغيل محرك: {task_func.__name__}")
            await task_func(*args)
        except Exception as e:
            logging.error(f"🚨 انهيار في {task_func.__name__}: {e}")
            logging.info("♻️ إعادة التشغيل التلقائي الآن...")
            await asyncio.sleep(10) # انتظار بسيط لتجنب التكرار السريع عند الخطأ


async def auto_evaluation_scheduler():
    """
    مجدول زمني شبحي يعمل في الخلفية لتقييم الصفقات كل 12 ساعة.
    """
    while True:
        try:
            print(f"🔄 [مجدول التقييم] بدء فحص الإشارات القديمة في: {datetime.now().strftime('%H:%M:%S')}")
            await evaluate_old_signals()
        except Exception as e:
            print(f"⚠️ خطأ في المجدول الزمني: {e}")
        
        # النوم لمدة 12 ساعة (بثواني) قبل الفحص التالي
        await asyncio.sleep(12 * 60 * 60)

# تعديل دالة main لتشغيل الخادم والرادار معاً
async def main_startup():
    # 👈 1. التقاط الـ Loop الرئيسي هنا
    main_loop = asyncio.get_running_loop()
    
    # 👈 2. إعداد اللوج مع تمرير الـ Loop للتلجرام
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(), 
            TelegramLoggerHandler(bot, GROUP_ID, main_loop) # تمرير main_loop
        ]
    )

    # أ) إعداد سيرفر الويب للبقاء Online (مهم للمنصات مثل Render/Heroku)
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/login', handle_telegram_login)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"🌐 Server Active on port {port}")

    # ب) تشغيل المحركات تحت حماية الـ WatchDog
    asyncio.create_task(watch_dog(forensic_investigation_cycle))
 
        
    # ج) تشغيل البوت الرئيسي (Aiogram) مع نظام إعادة المحاولة الصامد
    while True:
        try:
            logging.info("🚀 إقلاع محرك التليجرام... النظام تحت الحماية القصوى.")
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"❌ خطأ في البوت: {e}")
            logging.info("🔄 محاولة إعادة التشغيل تلقائياً خلال 10 ثوانٍ...")
            await asyncio.sleep(10)

if __name__ == '__main__':
    try:
        # تشغيل المحرك الرئيسي
        
        asyncio.run(main_startup())
    except KeyboardInterrupt:
        print("🛑 تم إيقاف النظام يدوياً من قبل أثير.")
    except Exception as e:
        # 🟢 طباعة إجبارية باللون الأحمر في راندر لكشف الخطأ القاتل
        print("\n" + "❌"*20)
        print(f"💥 انهيار قاتل منع البوت من الإقلاع:")
        print(f"{type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        print("❌"*20 + "\n")
        
        logging.critical(f"💥 انهيار غير متوقع في النظام: {e}")
