import os
import json
import tempfile
from io import BytesIO

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pypdf import PdfReader, PdfWriter
import requests

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID"))
DEEPSEEK_TOKEN = os.getenv("DEEPSEEKTOKEN")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

user_state = {}
user_pdf = {}
user_pages = {}


async def check_admin(update: Update) -> bool:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized.")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    await update.message.reply_text(
        "PDF Weaver — send me a PDF file to extract pages from it."
    )


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return

    user_id = update.effective_user.id

    file = await update.message.document.get_file()
    pdf_bytes = await file.download_as_bytearray()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(pdf_bytes)
    tmp.close()

    user_pdf[user_id] = tmp.name
    reader = PdfReader(tmp.name)
    page_count = len(reader.pages)
    user_state[user_id] = "AWAITING_PAGES"

    await update.message.reply_text(
        f"PDF received — {page_count} pages.\n\n"
        "Which pages do you want? Write in free language.\n"
        'e.g. "pages 5-7 and 10" or "עמוד 5 שאלה 4"'
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = user_state.get(user_id)

    if state == "AWAITING_PAGES":
        await process_page_request(update, user_id, text)
    elif state == "AWAITING_DEVIATION":
        await process_deviation(update, user_id, text)
    else:
        await update.message.reply_text("Send me a PDF file first.")


async def process_page_request(update: Update, user_id: int, text: str):
    pages = await extract_pages(text)

    if not pages:
        await update.message.reply_text(
            "Could not find any page numbers. Try again with clearer references."
        )
        return

    user_pages[user_id] = pages
    user_state[user_id] = "AWAITING_DEVIATION"

    pages_str = ", ".join(str(p) for p in pages)
    await update.message.reply_text(
        f"Pages extracted: [{pages_str}]\n\n"
        "What PDF page number corresponds to book page 1?\n"
        "(e.g. if book page 1 is on PDF page 10, enter 10.\n"
        "If no offset, enter 1)"
    )


async def process_deviation(update: Update, user_id: int, text: str):
    try:
        pdf_page_for_book_1 = int(text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return

    deviation = pdf_page_for_book_1 - 1
    pages = user_pages.get(user_id, [])
    pdf_path = user_pdf.pop(user_id, None)

    if not pdf_path:
        await update.message.reply_text("Error: PDF lost. Please send it again.")
        user_state[user_id] = "IDLE"
        return

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    writer = PdfWriter()
    used = []
    missing = []

    for book_page in sorted(set(pages)):
        pdf_page_index = book_page + deviation - 1
        if 0 <= pdf_page_index < total_pages:
            writer.add_page(reader.pages[pdf_page_index])
            used.append(book_page)
        else:
            missing.append(book_page)

    os.unlink(pdf_path)

    if not used:
        await update.message.reply_text("None of the requested pages fall within the PDF range.")
        user_state[user_id] = "IDLE"
        return

    output = BytesIO()
    writer.write(output)
    output.seek(0)

    caption = f"Book pages: {', '.join(str(p) for p in used)}"
    if missing:
        caption += f"\n(Out of range: {', '.join(str(p) for p in missing)})"

    await update.message.reply_document(
        document=output,
        filename="extracted.pdf",
        caption=caption,
    )

    user_state[user_id] = "IDLE"


async def extract_pages(text: str) -> list[int]:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_TOKEN}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "Extract page numbers from the user's request. Return ONLY a JSON array of integers. "
        "Expand ranges. Sort ascending. No duplicates.\n"
        'Examples:\n"pages 5-7 and 10" -> [5,6,7,10]\n'
        '"עמוד 5 שאלה 4" -> [5]\n'
        '"from page 3 to 6" -> [3,4,5,6]\n'
        '"pages 1, 3, 5" -> [1,3,5]\n'
        "If no page numbers found, return []."
    )

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
    }

    try:
        resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else ""
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        pages = json.loads(content)
        if isinstance(pages, list) and all(isinstance(p, int) for p in pages):
            return sorted(set(pages))
    except Exception as e:
        print(f"DeepSeek error: {e}")

    return []


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.MimeType("application/pdf"), handle_pdf))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
