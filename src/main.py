import logging
import datetime
import threading
import asyncio
import os
import constants
import db_storage as storage
import commands
from api import start_api
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
)
from machine import Machine
from double_confirm import create_double_confirm
from select_house import select_house_completed
from status_select_house import create_status_select_house
from set_timer_machine import set_timer_machine
from select_duration import select_duration
from convo_timeout import timeout_on_callback_query, timeout_on_message
from config import config, read_dotenv
from utils import with_house_context, with_deleted_previous_keyboards

read_dotenv()
storage.read_timers()
storage.read_house()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

logger = logging.getLogger("main")

MACHINES = {}
for house_id in constants.HOUSES.keys():
    MACHINES.update(
        {
            house_id: dict(
                [
                    [machine_name, Machine(house_id, machine_name)]
                    for machine_name in constants.MACHINE_NAMES
                ]
            )
        }
    )

COMMANDS_DICT = {
    "start": "Display help page",
    "select": constants.SELECT_COMMAND_DESCRIPTION,
    "status": constants.STATUS_COMMAND_DESCRIPTION,
}


async def setup_bot_commands(application: Application):
    """Set up bot commands asynchronously."""
    await application.bot.set_my_commands(list(COMMANDS_DICT.items()))
    logger.info("Bot commands registered successfully")


async def error_handler(update: object, context: CallbackContext) -> None:
    """Handle errors in the bot."""
    logger.error(f"Update {update} caused error: {context.error}")


def main():
    application = (
        Application.builder().token(config.get("TELEGRAM_BOT_API_KEY")).build()
    )

    # Register commands on startup
    application.post_init = setup_bot_commands

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", commands.start),
            CommandHandler(
                "select",
                with_deleted_previous_keyboards(
                    with_house_context(commands.create_select_menu())
                ),
            ),
            CommandHandler(
                "status",
                with_deleted_previous_keyboards(
                    with_house_context(commands.create_status_command(MACHINES))
                ),
            ),
        ],
        states={
            constants.ConvState.RequestConfirmSelect: [
                CallbackQueryHandler(backtomenu, pattern=r"^cancel$"),
                CallbackQueryHandler(create_double_confirm(MACHINES)),
            ],
            constants.ConvState.ConfirmSelect: [
                CallbackQueryHandler(backtomenu, pattern=r"^no$"),
                CallbackQueryHandler(
                    set_timer_machine(MACHINES), pattern=r"^yes|.*|.*$"
                ),
            ],
            constants.ConvState.SelectDuration: [
                CallbackQueryHandler(select_duration(MACHINES)),
            ],
            constants.ConvState.SelectHouse: [
                CallbackQueryHandler(select_house_completed)
            ],
            constants.ConvState.StatusSelectHouse: [
                CallbackQueryHandler(create_status_select_house(MACHINES))
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(None, timeout_on_message),
                CallbackQueryHandler(timeout_on_callback_query),
            ],
        },
        fallbacks=[],
        allow_reentry=True,
        conversation_timeout=datetime.timedelta(
            seconds=config.get("CONVO_TIMEOUT_SECONDS", 300)
        ),
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    application.job_queue.run_repeating(
        send_alarms, interval=datetime.timedelta(seconds=30)
    )

    threading.Thread(target=start_api, daemon=True).start()

    # Check for production mode via env var or config
    is_production = os.environ.get("PRODUCTION", "").lower() == "true" or config.get("PRODUCTION")

    if is_production:
        webhook_url = os.environ.get("WEBHOOK_URL") or config.get("WEBHOOK_URL")
        port = int(os.environ.get("PORT", config.get("PORT", 8443)))

        if webhook_url:
            logger.info(f"Running on webhook: {webhook_url}")
            application.run_webhook(
                listen="0.0.0.0",
                port=port,
                webhook_url=webhook_url,
            )
        else:
            logger.warning("PRODUCTION=true but no WEBHOOK_URL set, falling back to polling")
            application.run_polling(drop_pending_updates=True)
    else:
        logger.info("Running in polling mode")
        application.run_polling(drop_pending_updates=True)


async def send_alarms(context: CallbackContext):
    """Check and send due alarms."""
    for curr_user, chat_id, thread_id, machine_house_name in storage.check_alarms():
        logger.info(f"Sending alarm to {curr_user} in chat {chat_id}#{thread_id}")
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=f"@{curr_user} your clothes from {machine_house_name} are ready for collection! Please collect them now so that others may use it!",
        )


async def backtomenu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(constants.WELCOME_MESSAGE)


if __name__ == "__main__":
    main()
