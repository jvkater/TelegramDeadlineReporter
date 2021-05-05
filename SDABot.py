from telegram import Update, ReplyKeyboardMarkup, Bot, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from telegram.error import BadRequest, NetworkError
import logging
import datetime, pytz
import pandas as pd
import sqlite3
import re

# Disable SettingWithCopyWarning that arises from the way I handle personal dealdines.
pd.options.mode.chained_assignment = None

# Import of deadline data from the source file. Sheet name is specific for the Term that was currently underway.
df = pd.read_excel('Term2DL.xlsx', sheet_name="Term 5")


def next_weekday(d, weekday):
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    else:
        days_ahead += 7
    return d + datetime.timedelta(days_ahead)


def prepare_output(frame):
    '''Function to create an output sequence.
        Input: Pre-filtered DataFrame with deadlines
        Output: String that is being fed to bot output
    '''
    outp_string = ""
    if len(frame) == 0:
        return "Seems like there are no deadlines due in this period.\n"
    else:
        for i in frame.values:
            outp_string += "Subject: "
            outp_string += i[0]
            outp_string += "\n"
            outp_string += "Assignment: "
            outp_string += i[1]
            outp_string += "\n"
            outp_string += "Date: "
            try:
                outp_string += datetime.datetime.strftime(i[2], "%d-%b-%Y")
            except:
                outp_string += "TBD"
            outp_string += "\n"
            outp_string += "Weight: "
            outp_string += "{:.0%}".format(i[4])
            outp_string += "\n"
            outp_string += "\n"
        return outp_string


def get_deadlines(param):
    '''
    Function processes DataFrame with deadlines and sends the result to output processing function.
    Param var is responsible for distinguishing between cases:
        - param == 0: Need to return all deadlines yet to be due
        - param == 1: Need to return all deadlines within next week.
    '''
    today = datetime.datetime.today()
    df['Date'] = pd.to_datetime(df['Date'])
    df_new = df[df['Date'] >= today]
    if param == 1:
        next_sunday = next_weekday(today, 6)  # 0 = Monday, 1=Tuesday, 2=Wednesday...
        df_new = df_new[df_new['Date'] <= next_sunday]
    df_new = df_new.sort_values(by="Date")
    return prepare_output(df_new)


def get_personal_deadlines(frame):
    """
    Function to get deadlines based on input from SQL db
    :param frame: unfiltered DataFrame, result of SQL db query
    :return: string that is being fed to bot output
    """
    today = datetime.datetime.today()
    frame['duedate'] = pd.to_datetime(frame['duedate'], format="%d/%m/%Y")
    df_new = frame[frame['duedate'] >= today]
    df_new = df_new.sort_values(by="duedate")
    if len(df_new) == 0:
        outp_string = "Oops, seems you have not added any tasks yet. \n\n"
    else:
        outp_string = ""
        for i in df_new.values:
            outp_string += "Task: " + i[2] + "\n"
            outp_string += "Deadline: " + datetime.datetime.strftime(i[3], "%d-%b-%Y") + "\n\n"

    return outp_string


def subscriptions_apply_SQL(update, prelim, weekly):
    """
    Function to introduce changes to existing SQL database.
    :param update: link variable that connects bot conversation to the function
    :param prelim: binary variable to identify if a user is willing to receive updates a day before the deadline
    :param weekly: binary variable to identify if a user is willing to receive updates a week before the deadline
    :return: commited changes to the database
    """
    subs_db = sqlite3.connect("Subscriptions.db")
    subs_cursor = subs_db.cursor()
    subs_cursor.execute("INSERT INTO subscriptions VALUES (?,?,?,?);",
                        (update.message.from_user.full_name, update.message.chat_id, prelim, weekly))
    subs_db.commit()
    subs_db.close()


bot_token = #insert token here
updater = Updater(token=bot_token, use_context=True)
dispatcher = updater.dispatcher
bot = Bot(token=bot_token)
job = updater.job_queue

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    handlers=[
                        logging.FileHandler('convlogs.txt', mode='a'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

L1, DATEMODE, COURSEMODE, SUBSCRIPTIONSETTINGS, COURSEONLY, \
PERSONALENTRY, PERSONALDATE, PERSONALADDED, PERSONALEXIT, \
PERSONALEDITENTRY, PERSONALEDITACTION, PERSONALEDITINPUT = range(12)


#Conversation functions

def start(update: Update, context: CallbackContext):
    """
    Initiates the conversation, presents inline keyboard with options
    :param update: link to a bot
    :param context: context variable
    :return: next level of conversation
    """
    reply_keyboard = [['Date', 'Course'],['Personal deadlines','Reminders']]
    update.message.reply_text("Hey, good to see you! \n"
                              "Here's how it works:.\n"
                              "- In the first line of options you can select how to get info about study courses: by date or by course.\n"
                              "- The next line of options will allow you to add and edit personal deadlines or subscibe to reminders.",
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                                               one_time_keyboard=True))
    user = update.message.from_user
    logger.info("User %s entered main menu", user.full_name)
    return L1


def date(update: Update, context: CallbackContext):
    """
    Handles selection of date reply from the start function
    :param update: link to a bot
    :param context: conversation context
    :return: next level of conversation within the date tree depending on the selection
    """
    user = update.message.from_user
    logger.info("User %s selected date tree", user.full_name)
    reply_keyboard = [['By next Sunday', 'Show all']]
    update.message.reply_text("Cool! Now choose if you want to see the nearest deadlines or all",
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                                               one_time_keyboard=True))
    return DATEMODE


def course(update, context):
    """
    Handles selection of Course in the start function
    :param update: link to a bot
    :param context: context variable
    :return: next stage of the conversation depending on the selection
    """
    user = update.message.from_user
    logger.info("User %s selected course tree", user.full_name)
    reply_keyboard = [['Show all courses', 'Show specific course']]
    update.message.reply_text("Cool! Now choose how you want to see this information",
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                                               one_time_keyboard=True))
    return COURSEMODE


def personal(update, context):
    """
    Handles selection of personal deadlines in start function
    :param update: link to a bot
    :param context: context variable
    :return: Next stage of conversation
    """
    user = update.message.from_user
    logger.info("User %s selected personal tree", user.full_name)
    reply_keyboard = [['See personal deadlines'], ['Add personal deadlines'], ['Edit personal deadlines']]
    update.message.reply_text("Cool! Now choose what you would like to access",
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                                               one_time_keyboard=True))
    return PERSONALENTRY


def next_sunday(update: Update, context: CallbackContext):
    """
    Handles selection of "By next Sunday" in the previous stage of the date tree.
    Calls get_deadlines function with parameter 1 that stands for "next sunday".
    Execution of get_deadlines returns a string and sends it to a user.
    :param update: link to a bot
    :param context: context variable
    :return: This function ends the conversation
    """
    update.message.reply_text(get_deadlines(1))
    logger.info("User %s asked for next Sunday deadlines", update.message.from_user.full_name)
    update.message.reply_text("\n \n Click --> /start to return to menu ")
    return ConversationHandler.END


def all_deadlines(update, context):
    """
    Handles selection of "all" in the previous stage of the date tree.
    Calls get_deadlines function with parameter 0 that leads to no filters applied.
    Execution of get_deadlines returns a string and sends it to a user.
    :param update: link to a bot
    :param context: context variable
    :return:  This function ends the conversation
    """
    user = update.message.from_user
    logger.info("User %s asked for all deadlines", user.full_name)
    update.message.reply_text(get_deadlines(0))
    update.message.reply_text("\n \n Click --> /start to return to menu")
    return ConversationHandler.END


def all_courses(update, context):
    """
    Handles selection of "Show all courses" in course tree.
    Takes DataFrame with all courses and sorts it by course, prints out the result to user through prepare_output
    :param update: link to a bot
    :param context: context variable
    :return: Ends the conversation
    """
    user = update.message.from_user
    logger.info("User %s asked for all courses", user.full_name)
    update.message.reply_text(prepare_output(df.sort_values(by="Course")))
    update.message.reply_text("\n \n Click --> /start to return to menu ")
    return ConversationHandler.END


def course_selection(update, context):
    """
    Handles selection of "Show specific course" in the course tree.
    Takes unique values from the "Course" column in the DataFrame and prints it out to user in column
    :param update: link to a bot
    :param context: context variable
    :return: Next stage of the conversation in the course tree
    """
    reply_options = [[x] for x in set(df['Course'].values)]
    update.message.reply_text("Cool! Now choose how you want to see this information",
                              reply_markup=ReplyKeyboardMarkup(reply_options, resize_keyboard=True,
                                                               one_time_keyboard=True))
    return COURSEONLY


def print_course(update, context):
    """
    Handles selection of a specific course from the previous stage of the course tree.
    Filters out the original DataFrame according to the user selection on the previous step
    :param update: link to a bot
    :param context: context variable
    :return: Ends the conversation
    """
    logger.info("User %s asked for specific course", update.message.from_user.full_name)
    selection = update.message.text
    update.message.reply_text("You have chosen " + selection)
    update.message.reply_text(prepare_output(df[df['Course'] == selection]))
    update.message.reply_text("\n \n Click --> /start to return to menu ")
    return ConversationHandler.END


def see_personal(update, context):
    """
    Function handles selection of "Personal deadlines" in the start screen.
    Sends request to the SQL db, filters out the results to match user full name, prints out the results to a user.
    :param update: link to a bot
    :param context: context variable
    :return: Ends the conversation
    """
    logger.info('User '+update.message.from_user.full_name+" went to see personal deadlines")
    todoDB = sqlite3.connect('2DO.db')
    fetchedDB = pd.read_sql_query("SELECT * FROM tasks", todoDB)
    todoDB.close()
    personalDB = fetchedDB[fetchedDB['username'] == update.message.from_user.full_name]
    update.message.reply_text(get_personal_deadlines(personalDB)+"Click --> /start to return to menu ")
    return ConversationHandler.END


def add_personal(update, context):
    """
    Polling function that handles the "Add personal deadline" behaviour.
    Prints a conversation text asking for user input, which will be processed on the next stage of the conversation.
    :param update: link to a bot
    :param context: context variable
    :return: Next stage of a conversation
    """
    update.message.reply_text('Type and send the task description you want to add')
    return PERSONALDATE


def edit_personal_selection(update, context):
    """
    Handles selection of "Edit personal deadline" behaviour in the personal tree.
    :param update: link to a bot
    :param context: context variable
    :return: Next stage of a conversation
    """
    logger.info("User "+ update.message.from_user.full_name + " wants to edit personal deadlines")
    reply_keyboard = [['Change task description'], ['Change task deadline'],['Delete task']]
    update.message.reply_text("Please select what you'd like to do",
                              reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,one_time_keyboard=True))
    return PERSONALEDITENTRY


def edit_personal_course_selection(update,context):
    """
    Function handles selection of either "Change task" options on the previous step in the personal tree.
    Performs request to DB to check if the user exists.
        If exists, it prints out a list of tasks stored
        If not, it prints out message indicating no tasks and ends the conversation.
    :param update: link to a bot
    :param context: context variable
    :return: If tasks exist, proceeds with the sequence. Otherwise it ends the conversation.
    """
    todoDB = sqlite3.connect('2DO.db')
    fetchedDB = pd.read_sql_query("SELECT * FROM tasks", todoDB)
    todoDB.close()
    personalDB = fetchedDB[fetchedDB['username'] == update.message.from_user.full_name]
    context.user_data['action']= update.message.text
    logger.info("User "+ update.message.from_user.full_name + " wants to " + update.message.text)

    if len(personalDB) == 0:
        update.message.reply_text("Seems like you don't have any tasks added yet.\n\nClick --> /start to start over and add a task")
        return ConversationHandler.END
    else:
        reply_keyboard = [[x] for x in personalDB['description']]
        update.message.reply_text("Please select a task that you'd like to modify",
                                  reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                                                   one_time_keyboard=True))
        return PERSONALEDITACTION


def edit_personal_action(update, context):
    """
    Function handles selection of "Edit task" option on the previous step in the personal tree
    :param update: link to a bot
    :param context: context variable
    :return: Depends on the input on the previous step.
    Performs a deletion if this option was selected and terminates the conversation.
    Otherwise proceeds to the next stage.
    """
    context.user_data['task'] = update.message.text
    if context.user_data['action'] == 'Delete task':
        logger.info("User " + update.message.from_user.full_name + " wants to delete personal deadline")
        todoDB = sqlite3.connect('2DO.db')
        cursor = todoDB.cursor()
        cursor.execute("DELETE FROM tasks WHERE username = ? AND description = ?",
                       (update.message.from_user.full_name, update.message.text))
        todoDB.commit()
        todoDB.close()
        update.message.reply_text("Task was successfully deleted.\n\nClick --> /start to return to menu")
        return ConversationHandler.END
    elif context.user_data['action'] == 'Change task description':
        logger.info("User "+update.message.from_user.full_name + " wants to change task description")
        update.message.reply_text("Please enter the new description")
        return PERSONALEDITINPUT
    else:
        logger.info("User "+update.message.from_user.full_name + " wants to change task deadline")
        update.message.reply_text("Please enter the new deadline using format dd/mm/yyyy (e.g. 28/02/2021)")
        return PERSONALEDITINPUT


def edit_personal_modification(update, context):
    """
    Function to execute modification of a personal task selected on a previous stage of the personal tree.
    :param update: link to a bot
    :param context: context variable
    :return: Commits the changes and ends the conversation.
    """
    todoDB = sqlite3.connect('2DO.db')
    cursor = todoDB.cursor()
    if context.user_data['action'] == 'Change task description':
        cursor.execute('UPDATE tasks SET description = ? WHERE username = ? AND description = ?',
                       (update.message.text, update.message.from_user.full_name, context.user_data['task']))
        logger.info("User " + update.message.from_user.full_name + " have modified personal task description")
    elif context.user_data['action'] == 'Change task deadline':
        cursor.execute('UPDATE tasks SET duedate = ? WHERE username = ? AND description = ?',
                       (update.message.text, update.message.from_user.full_name, context.user_data['task']))
        logger.info("User " + update.message.from_user.full_name + " have modified personal task deadline")
    else:
        logger.info("User typed unrecognized command, SQL will not be executed")
    todoDB.commit()
    todoDB.close()
    update.message.reply_text("Task has been successfully updated! \n\nClick --> /start to return to menu")
    return ConversationHandler.END


def add_personal_date(update, context):
    """
    Polling function that asks for a new deadline date in personal task modification
    :param update: link to a bot
    :param context: context variable
    :return: Next stage of the conversation
    """
    context.user_data['description'] = update.message.text
    update.message.reply_text('Please add deadline in format dd/mm/yyyy (e.g. 28/02/2021)')
    return PERSONALADDED


def after_added(update, context):
    """
    Function that executes the insertion into the database and ends the "Add personal" tree
    :param update: link to a bot
    :param context: context variable
    :return: Selection of Personal deadlines or exit
    """
    todoDB = sqlite3.connect('2DO.db')
    cursor = todoDB.cursor()
    logger.info("User %s added personal deadline", update.message.from_user.full_name)
    reply_keyboard = [['See personal deadlines', 'Return to main menu']]
    update.message.reply_text("Cool! Now choose what you would like to do next",
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                                               one_time_keyboard=True))
    cursor.execute("INSERT INTO tasks VALUES (?,?,?,?);",
                   (update.message.from_user.full_name, update.message.chat_id, context.user_data['description'], update.message.text))
    todoDB.commit()
    todoDB.close()
    return PERSONALEXIT


def subscription_settings(update, context):
    """
    Function that prints out different subscription options along with a short description.
    :param update: link to a bot
    :param context: context variable
    :return: Next stage of the conversation
    """
    logger.info("User " + update.message.from_user.full_name + " went to subscription settings")
    reply_options = [['24h reminder','Sunday reminder'], ['Both', 'Cancel reminders']]
    update.message.reply_text('Please choose one of the available options: \n'
                              '- 24h reminder will send you info about deadlines that are due tomorrow;\n'
                              '- Sunday notifications will send you info about deadlines in the upcoming week;\n'
                              '- Or choose to receive both types of notifications.\n'
                              '\n You can also manage notifications if you no longer want to receive any of them. ',
                              reply_markup=ReplyKeyboardMarkup(reply_options, one_time_keyboard=True, resize_keyboard=True))

    return SUBSCRIPTIONSETTINGS


def subscriptions_apply(update, context):
    """
    Function to fetch user choice from the previous stage and write the changes to the database.
    :param update: link to a bot
    :param context: context variable
    :return: End of the conversation
    """
    selection = update.message.text
    logger.info("User " + update.message.from_user.full_name + " selected " + update.message.text)

    if selection == "Both":
        subscriptions_apply_SQL(update, 1, 1)
    elif selection == "24h reminder":
        subscriptions_apply_SQL(update, 1, 0)
    elif selection == "Sunday reminder":
        subscriptions_apply_SQL(update, 0, 1)
    elif selection == "Cancel reminders":
        subs_db = sqlite3.connect("Subscriptions.db")
        subs_cursor = subs_db.cursor()
        subs_cursor.execute("DELETE FROM subscriptions WHERE username = ?;",(update.message.from_user.full_name,))
        subs_db.commit()
        subs_db.close()
    update.message.reply_text("Thanks! The settings have been updated\n\nClick --> /start to return to menu")
    return ConversationHandler.END


def help(update, context):
    """
    [LEGACY] Logger function to notify user that the thing he typed is not supported.
    :param update: link to a bot
    :param context: context variable
    :return: Ends the conversation after logging and printing out the message
    """
    update.message.reply_text("seems like I don't know this command yet!")
    user = update.message.from_user
    logger.info("User " + user.first_name + " typed " + update.message.text)
    update.message.reply_text("\n \n Click --> /start to return to menu ")
    return ConversationHandler.END


def timeout(update, context):
    """
    Handler and logger of timeout event. The event itself is set in the conversation outside of the function.
    :param update: link to a bot
    :param context: context variable
    :return: Ends the conversation
    """
    user = update.message.from_user
    logger.info("User " + user.full_name + " ran out of time")
    update.message.reply_text("You haven't selected anything in a minute, so I'm terminating this conversation\n \n"
                              "Click --> /start to return to menu ", reply_markup=ReplyKeyboardRemove(True))
    return ConversationHandler.END


def error_handler(update, context):
    try:
        raise context.error
    except BadRequest:
        logger.info("An empty message exception occurred")
    except NetworkError:
        logger.info("A network error occurred")

'''Job functions'''

def daily_reminder(context):
    """
    Function to perform daily reminder mailout.
    First it takes the deadlines DataFrame, analyses if any of line items are due tomorrow.
    Then it analyses if there are any customers that have subscribed to the daily notifications and sends messages to them.
    :param context: context variable
    :return: Standard message sent to subscribed users.
    """
    today = datetime.datetime.today()
    tomorrow = datetime.datetime.today() + datetime.timedelta(days=1)
    df_new = df[df['Date'] >= today]
    df_new = df_new[df_new['Date'] <= tomorrow]
    subs_db = sqlite3.connect('Subscriptions.db')
    mailout_list = pd.read_sql_query("SELECT * FROM subscriptions", subs_db)
    subs_db.close()
    personal_db = sqlite3.connect('2DO.db')
    tasks_list = pd.read_sql_query("SELECT * FROM tasks", personal_db)
    tasks_list['duedate'] = pd.to_datetime(tasks_list['duedate'], format="%d/%m/%Y")
    personal_db.close()
    personal_tomorrow = tasks_list[tasks_list['duedate']>=today]
    personal_tomorrow = personal_tomorrow[personal_tomorrow['duedate']<=tomorrow]
    tomorrow_list = mailout_list[mailout_list['upcoming'] == 1]
    tomorrow_list.drop_duplicates(inplace=True)
    for i in tomorrow_list['chat_id']:
        personal_task_list = personal_tomorrow[personal_tomorrow['chat_id']==i]
        if len(df_new)>0 and len(personal_task_list)>0:
            output_text = 'Hi! There are some tasks due tomorrow!\n\n'
            output_text+=prepare_output(df_new)
            output_text+="And also something personal\n\n"
            output_text+=get_personal_deadlines(personal_task_list)
            output_text+='Click --> /start to go to menu'
            context.bot.send_message(chat_id=i, text=output_text)
        elif len(df_new)==0 and len(personal_task_list)>0:
            output_text = 'Hi! There are some tasks due tomorrow!\n\n'
            output_text += get_personal_deadlines(personal_task_list)
            output_text += 'Click --> /start to go to menu'
            context.bot.send_message(chat_id=i, text=output_text)
        elif len(df_new)>0 and len(personal_task_list)==0:
            output_text = 'Hi! There are some tasks due tomorrow!\n\n'
            output_text += prepare_output(df_new)
            output_text += 'Click --> /start to go to menu'
            context.bot.send_message(chat_id=i, text=output_text)
        else:
            continue

def weekly_reminder(context):
    """
    Function to perform weekly reminder mailout.
    First it takes the deadlines DataFrame, analyses if any of line items are due till Sunday next week.
    Then it analyses if there are any customers that have subscribed to the daily notifications and sends messages to them.
    :param context: context variable
    :return: Standard message sent to subscribed users.
    """
    today = datetime.datetime.today()
    week_more = datetime.datetime.today() + datetime.timedelta(days=7)
    df_new = df[df['Date'] >= today]
    df_new = df_new[df_new['Date'] <= week_more]
    subs_db = sqlite3.connect('Subscriptions.db')
    mailout_list = pd.read_sql_query("SELECT * FROM subscriptions", subs_db)
    subs_db.close()
    personal_db = sqlite3.connect('2DO.db')
    tasks_list = pd.read_sql_query("SELECT * FROM tasks", personal_db)
    tasks_list['duedate'] = pd.to_datetime(tasks_list['duedate'], format="%d/%m/%Y")
    personal_db.close()
    personal_next_week = tasks_list[tasks_list['duedate']>=today]
    personal_next_week = personal_next_week[personal_next_week['duedate']<=week_more]
    tomorrow_list = mailout_list[mailout_list['upcoming'] == 1]
    tomorrow_list.drop_duplicates(inplace=True)
    for i in tomorrow_list['chat_id']:
        personal_task_list = personal_next_week[personal_next_week['chat_id']==i]
        if len(df_new)>0 and len(personal_task_list)>0:
            output_text = 'Hi! There are some tasks due next week!\n\n'
            output_text+=prepare_output(df_new)
            output_text+="And also something personal\n\n"
            output_text+=get_personal_deadlines(personal_task_list)
            output_text+='Click --> /start to go to menu'
            context.bot.send_message(chat_id=i, text=output_text)
        elif len(df_new)==0 and len(personal_task_list)>0:
            output_text = 'Hi! There are some tasks due next week!\n\n'
            output_text += get_personal_deadlines(personal_task_list)
            output_text += 'Click --> /start to go to menu'
            context.bot.send_message(chat_id=i, text=output_text)
        elif len(df_new)>0 and len(personal_task_list)==0:
            output_text = 'Hi! There are some tasks due next week!\n\n'
            output_text += prepare_output(df_new)
            output_text += 'Click --> /start to go to menu'
            context.bot.send_message(chat_id=i, text=output_text)
        else:
            continue


'''Main body'''

conversation = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        L1: [MessageHandler(Filters.regex('Date'), date), MessageHandler(Filters.regex('Course'), course),
             MessageHandler(Filters.regex('Personal'), personal),
             MessageHandler(Filters.regex('Reminders'), subscription_settings)],
        SUBSCRIPTIONSETTINGS: [MessageHandler(Filters.text, subscriptions_apply)],
        DATEMODE: [MessageHandler(Filters.regex('By next Sunday'), next_sunday),
                   MessageHandler(Filters.regex('Show all'), all_deadlines)],
        COURSEMODE: [MessageHandler(Filters.regex('Show all courses'), all_courses),
                     MessageHandler(Filters.regex('Show specific course'), course_selection)],
        COURSEONLY: [MessageHandler(Filters.text, print_course)],
        PERSONALENTRY: [MessageHandler(Filters.regex('See personal deadlines'), see_personal),
                        MessageHandler(Filters.regex('Add personal deadlines'), add_personal),
                        MessageHandler(Filters.regex('Edit personal deadlines'), edit_personal_selection)],
        PERSONALDATE: [MessageHandler(Filters.text, add_personal_date)],
        PERSONALADDED: [MessageHandler(Filters.text, after_added)],
        PERSONALEDITENTRY: [MessageHandler(Filters.text, edit_personal_course_selection)],
        PERSONALEDITACTION: [MessageHandler(Filters.text,edit_personal_action)],
        PERSONALEDITINPUT:[MessageHandler(Filters.text,edit_personal_modification)],
        PERSONALEXIT: [MessageHandler(Filters.regex('See personal deadlines'), see_personal),
                       MessageHandler(Filters.regex('Return to main menu'), start)],
        ConversationHandler.TIMEOUT: [MessageHandler(Filters.text, timeout)]
    },
    conversation_timeout=60,
    fallbacks=[MessageHandler(Filters.text, help)]
)

#Support for commands that existed in the previous versions of the bot because some people kept reusing them
legacy_next = CommandHandler('next', next_sunday)
legacy_course = CommandHandler('course', all_courses)
legacy_study = CommandHandler('study', all_deadlines)
legacy_next_sunday = MessageHandler(Filters.regex(re.compile(r'By next Sunday', re.IGNORECASE)), next_sunday)

job.run_daily(daily_reminder, time=datetime.time(10,8,00,tzinfo=pytz.timezone("CET")))
job.run_daily(weekly_reminder, time=datetime.time(19,0,00,tzinfo=pytz.timezone("CET")), days=[6])

dispatcher.add_handler(conversation)
dispatcher.add_error_handler(error_handler)
dispatcher.add_handler(legacy_next)
dispatcher.add_handler(legacy_course)
dispatcher.add_handler(legacy_study)
dispatcher.add_handler(legacy_next_sunday)

updater.start_polling()