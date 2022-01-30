from telegram import (
    Update,
    Poll,
    Chat,
    ChatMember,
    ParseMode,
    ChatMemberUpdated,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    MessageHandler,
    Filters,
    ChatMemberHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    PollHandler,
)


from datetime import datetime, timedelta
import os.path
import pandas as pd
from ast import literal_eval
from random import random
from pony.orm import *

db = Database()

# PostgreSQL
db.bind(provider='postgres',
        user='postgres',
        password='telegrambot',
        host='localhost',
        database='telebot_db')

class MeetingDB(db.Entity):
    #id = Required(int)
    index = Optional(int)
    meeting_name = Optional(str)
    creating_time = Optional(datetime) # datetime.now()
    status = Optional(str) # self.STATUS[0]
    actuality_up_to = Optional(datetime) # self.creating_time + timedelta(hours = self.TIME_TO_LIVE)
    invited = Optional(StrArray) # []
    options = Optional(Json) # []
    duration = Optional(int) # 1  # duration in hours
    voted = Optional(Json)
    waitfor = Optional(StrArray)
    user_id = Optional(int) #user.id
    username = Optional(str) # user.username
    user_firstname = Optional(str)
    result = Optional(StrArray)

class Meeting():
    TIME_TO_LIVE = 8
    STATUS = [
        'preparing',
        'active',
        'archive',
        'success',
        'failure'
    ]
    DB_FILE = 'db.csv'

    MODEL = MeetingDB

    def __init__(self, user, meeting_name = None, index = None):

        self.db = self.MODEL

        if index:
            self.load(index)
        else:
            self.index = None
            self.meeting_name = meeting_name
            self.creating_time = datetime.now()
            self.status = self.STATUS[0]
            self.actuality_up_to = self.creating_time + timedelta(hours = self.TIME_TO_LIVE)
            self.invited = []
            self.options = dict()
            self.duration = 1  # duration in hours
            self.voted = dict()
            self.waitfor = []
            self.user_id = user.id
            self.username = user.username
            self.user_firstname = user.first_name
            self.result = []

            self.create()

    def add_persons(self, names):
        if isinstance(names, list):
            self.invited += names
        else:
            self.invited.append(names)

        self.invited = list(set(self.invited))
        # self.waitfor = self.invited
        return self.invited

    def remove_persons(self, names):
        self.invited = list(set(self.invited) - set(names))
        return self.invited

    def add_options(self, opts):
        # print('add_options', opts)
        new = list(opts.values())
        old = list(self.options.values())
        all = set(new + old)
        self.options = {int(i): v for i, v in enumerate(all)}
        return self.options

    def remove_options(self, opts):
        new = list(opts.values())
        old = list(self.options.values())
        all = list(set(old) - set(new))
        self.options = {int(i): v for i, v in enumerate(list(all))}
        return self.options

    def run_voting(self):
        if len(self.options) < 2:
            return (False, 'at least two option must be')
        if len(self.invited) < 2:
            return (False, 'at least two participants are required')
        self.status = self.STATUS[1]
        self.waitfor = self.invited
        self.update()
        return (True, 'ok')

    def archivate_voting(self):
        self.status = self.STATUS[2]
        self.update()

    def change_duration(self, duration):
        self.duration = duration
        self.update()


    @db_session
    def update(self):
        options_to_str = {k: v.strftime('%d.%m.%Y %H:%M') for k, v in self.options.items()}
        result_to_str = [v.strftime('%d.%m.%Y %H:%M') for v in self.result]

        struc = {'index' : self.index,
                 'meeting_name': self.meeting_name,
                 'creating_time': self.creating_time,
                 'status': self.status,
                 'actuality_up_to': self.actuality_up_to,
                 'invited': self.invited,
                 'options': options_to_str,  # self.options,
                 'duration': self.duration,
                 'voted': self.voted,
                 'waitfor': self.waitfor,
                 'user_id': int(self.user_id),
                 'username': self.username,
                 'user_firstname': self.user_firstname,
                 'result': result_to_str}
        self.db[self.index].set(**struc)

    @db_session
    def create(self):
        items = [n.get_pk() for n in self.db.select()]
        if len(items) == 0:
            self.index = 1
        else:
            self.index = max(items) + 1
        struc = {'index' : self.index,
                 'meeting_name': self.meeting_name,
                 'creating_time': self.creating_time,
                 'status': self.status,
                 'actuality_up_to': self.actuality_up_to,
                 'invited': self.invited,
                 'options': self.options,
                 'duration': self.duration,
                 'voted': self.voted,
                 'waitfor': self.waitfor,
                 'user_id': int(self.user_id),
                 'username': self.username,
                 'user_firstname': self.user_firstname,

                 'result': self.result}
        self.db(**struc)

    @db_session
    def load(self, ind):
        meeting = self.db[ind]
        self.index = meeting.index
        self.meeting_name = meeting.meeting_name
        self.creating_time = meeting.creating_time
        self.status = meeting.status
        self.actuality_up_to = meeting.actuality_up_to
        self.invited = meeting.invited

        self.options = {int(k): datetime.strptime(t.strip(), '%d.%m.%Y %H:%M') for k, t in meeting.options.items()}
        self.duration = meeting.duration
        self.voted = meeting.voted

        self.waitfor = meeting.waitfor  # [] if item['waitfor'] == 0 else str(item['waitfor']).replace('[', '').replace(']', '').replace("'", '').split(', ')

        self.user_id = meeting.user_id
        self.username = meeting.username
        self.user_firstname = meeting.user_firstname
        self.result = [datetime.strptime(t.strip(), '%d.%m.%Y %H:%M') for t in meeting.result]

    def check_results(self):
        if len(self.waitfor) == 0:
            options = [set(v) for v in self.voted.values()]
            u = set.intersection(*options)
            if len(u) > 0:
                self.result = [self.options[k] for k in list(u)]
                self.status = self.STATUS[3]
            else:
                self.status = self.STATUS[4]

    def vote_done(self, username, options):
        # print('here voted:', options, len(self.options))
        if max(options) == len(self.options):
            self.voted[username] = []
        else:
            self.voted[username] = [int(o) for o in options]
        self.waitfor = [i for i in self.waitfor if i != username]

        self.check_results()
        self.update()

    def get_info(self):
        empty_margin = '                           '
        empty_line = f'\n{empty_margin}[empty]'

        respond = f'''
        <b>Meeting #{self.index}</b> <b>"{self.meeting_name}"</b> from <b>{self.user_firstname} ({self.username})</b> 
        
               created: {self.creating_time:%d.%m.%y %H:%M}
               espired: {self.actuality_up_to:%d.%m.%y %H:%M}
              duration: {self.duration} hours         {"[/change_duration]" if self.status == self.STATUS[0] else ""}
    current status: <b>{self.status}</b>       [{"/run" if self.status == self.STATUS[0] else ""} /archivate]
               invited:'''
        if len(self.invited) != 0:
            respond += ''.join([f'\n{empty_margin}-<b>{i}</b>' for i in self.invited])
        else:
            respond += empty_line
        if self.status == self.STATUS[0]:
            respond += '\n{empty_margin}  [/add_persons /remove_persons]'

        respond += \
        f'''
               options:'''
        if len(self.options.items()) != 0:
            respond += ''.join([f'\n{empty_margin}<pre>[{k}]</pre> ' + v.strftime("%d.%m.%Y %H:%M") for k, v in self.options.items()])
        else:
            respond += empty_line
        if self.status == self.STATUS[0]:
            respond += '\n{empty_margin}[/add_options /remove_options]'

        respond += \
        f'''
        already voted:'''
        if len(self.voted.items()) != 0:
            respond += ''.join([f'\n{empty_margin}- {k} for <pre>{v if len(v)>0 else "None above"}</pre>' for k, v in self.voted.items()])
        else:
            respond += empty_line

        respond += \
        f'''
          waiting for:'''
        if len(self.waitfor) != 0:
            respond += ''.join([f'\n{empty_margin}- {i}' for i in self.waitfor])
        else:
            respond += empty_line

        if self.status in {self.STATUS[3], self.STATUS[4]}:
            respond += \
            f'''
            
YOU'VE GOT RESULT: <b>{self.status}</b> '''
        if self.status == self.STATUS[3]:
            respond += 'Confirmed options: ' + ', '.join([f'{t.strftime("%d.%m.%Y %H:%M")}' for t in self.result])


        return respond

class UserMeetings():
    MODEL = MeetingDB

    def __init__(self, name):
        self.user = name
        self.my_ative_votings = []
        self.my_meetings = []
        self.current_meeting = None

    def start(self, name):
        self.user = None

    def create_new_meeting(self, name):
        self.current_meeting = Meeting(self.user, meeting_name=name)

    def get_info(self):
        if not self.current_meeting:
            return 'You should create /new_meeting <name> first'
        return self.current_meeting.get_info()

    @db_session
    def get_all_my_meeting(self):
        items = (select(m for m in self.MODEL if (m.username == self.user.username and m.status != 'archive')))
        my_meetings_id = [i.get_pk() for i in items]
        # print(my_meetings_id)
        self.my_meetings = [None] * len(my_meetings_id)
        for i, l_id in enumerate(my_meetings_id):
            # print(f'{l_id}')
            self.my_meetings[i] = Meeting(self.user, index=l_id)

    @db_session
    def get_voting_list(self):

        items = (select(m for m in self.MODEL if (self.user.username in m.waitfor and m.status != 'archive')))
        vote_id_list = [i.get_pk() for i in items]
        # print(vote_id_list)
        self.my_ative_votings = [None] * len(vote_id_list)
        for i, l_id in enumerate(vote_id_list):
            # print(f'{l_id}')
            self.my_ative_votings[i] = Meeting(self.user, index=l_id)

    def vote_done(self, meeting_id, options):
        self.my_ative_votings[meeting_id].vote_done(self.user.username, options)

def start(update: Update, context: CallbackContext):
    # print(update.effective_user)
    context.bot_data[update.effective_user] = dict()
    context.bot_data[update.effective_user]['UM'] = UserMeetings(update.effective_user)
    welcome = \
    f'''
    Hello <b>{update.effective_user.first_name}</b>!
    
    Welcome to the <b>Bot</b> for <b>Meeting Arrangements</b>! 
    
    You could:
    
    <b><pre>[1]</pre></b> Start your first meeting and invite contacts there by /new_meeting
    
    <pre>[2]</pre> Check your current meeting list and control your meetings /all_my_meetings
    
    <pre>[3]</pre> Check if you were asked to confirm convenient options for you and vote for appropriate one /voting_list  

    '''

    update.message.reply_text(welcome, parse_mode='HTML')

def authorized(update: Update, context: CallbackContext):
    user_obj = context.bot_data.get(update.effective_user, None)
    # print(update.effective_user)
    if update.effective_user not in context.bot_data.keys():
        context.bot_data[update.effective_user] = dict()
        context.bot_data[update.effective_user]['UM'] = UserMeetings(update.effective_user)
    else:
        if 'UM' not in context.bot_data[update.effective_user].keys():
            context.bot_data[update.effective_user]['UM'] = UserMeetings(update.effective_user)

def new_meeting(update: Update, context: CallbackContext):
    authorized(update, context)
    # context.bot_data[update.effective_user]['UM'] = user_obj
    context.bot_data[update.effective_user]['command'] = 'new_meeting'
    update.message.reply_text(f'Type the name of meeting:')

def meeting_info(update: Update, context: CallbackContext):
    info = context.bot_data[update.effective_user]['UM'].get_info()
    # update.message.reply_text(f'Hello {update.effective_user.first_name}')
    update.message.reply_text(info, parse_mode='HTML')

def all_my_meetings(update: Update, context: CallbackContext):
    authorized(update, context)
    context.bot_data[update.effective_user]['UM'].get_all_my_meeting()
    list_of_meetings = context.bot_data[update.effective_user]['UM'].my_meetings

    if len(list_of_meetings) == 0:
        update.message.reply_text(f'You have no invitiated any meetings. You could start with: /new_meeting')
        return None

    respond = 'You initiate:\n'
    respond = '<b>You initiate this meetings:</b>\n\n'

    for i, v in enumerate(list_of_meetings):
        respond += f'          <pre>[{i}]</pre> meeting <b>"{v.meeting_name}"</b> curently in status <b>{v.status}</b> with options:'
        for j, m in v.options.items():
            respond += f'\n                    - {m.strftime("%d.%m.%Y %H:%M")}'
        respond += '\n\n'
        # options = ', '.join([f'{k}) "{t.strftime("%d.%m.%Y %H:%M")}"' for k, t in v.options.items()])
        # respond += f'{i}) meeting "{v.meeting_name}" with options {options}\n'

    keyboard = [[f'/my_meeting {i}' for i in  range(len(list_of_meetings))]] + [['/all_my_meetings']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(respond, reply_markup=reply_markup, parse_mode='HTML')

def my_meeting(update: Update, context: CallbackContext):
    meeting_id = int(context.args[0])
    # print(meeting_id)
    context.bot_data[update.effective_user]['UM'].current_meeting = context.bot_data[update.effective_user]['UM'].my_meetings[meeting_id]

    # my_ative_votings[meeting_id]
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=context.bot_data[update.effective_user]['UM'].my_meetings[meeting_id].get_info(),
                             parse_mode='HTML')


def add_persons(update: Update, context: CallbackContext) -> None:
    status = context.bot_data[update.effective_user]['UM'].current_meeting.status
    if status != 'preparing':
        update.message.reply_text(f'you could change it only in "preparing" status')
        return None

    context.bot_data[update.effective_user]['command'] = 'add_persons'
    update.message.reply_text(f'Type the usernames: username1, [username2, ...]')

def remove_persons(update: Update, context: CallbackContext) -> None:
    status = context.bot_data[update.effective_user]['UM'].current_meeting.status
    if status != 'preparing':
        update.message.reply_text(f'you could change it only in "preparing" status')
        return None

    context.bot_data[update.effective_user]['command'] = 'remove_persons'
    update.message.reply_text(f'Type the usernames: username1, [username2, ...]')

def add_options(update: Update, context: CallbackContext) -> None:
    status = context.bot_data[update.effective_user]['UM'].current_meeting.status
    if status != 'preparing':
        update.message.reply_text(f'you could change it only in "preparing" status')
        return None
    context.bot_data[update.effective_user]['command'] = 'add_options'
    update.message.reply_text(f'Type start of meeting: dd.mm.yyyy HH:MM, [dd.mm.yyyy HH:MM, ...]')

def remove_options(update: Update, context: CallbackContext) -> None:
    status = context.bot_data[update.effective_user]['UM'].current_meeting.status
    if status != 'preparing':
        update.message.reply_text(f'you could change it only in "preparing" status')
        return None

    context.bot_data[update.effective_user]['command'] = 'remove_options'
    update.message.reply_text(f'Type start of meeting: dd.mm.yy HH:MM, [dd.mm.yy HH:MM, ...]')

def change_duration(update: Update, context: CallbackContext) -> None:
    status = context.bot_data[update.effective_user]['UM'].current_meeting.status
    if status != 'preparing':
        update.message.reply_text(f'you could change it only in "preparing" status')
        return None
    context.bot_data[update.effective_user]['command'] = 'change_duration'
    update.message.reply_text(f'Type duration in hours (ex: 1 or 1.5 )')


def run_voting(update: Update, context: CallbackContext) -> None:
    ok, message = context.bot_data[update.effective_user]['UM'].current_meeting.run_voting()
    if not ok:
        update.message.reply_text(message)
    update.message.reply_text(context.bot_data[update.effective_user]['UM'].get_info(), parse_mode='HTML')

def archivate_voting(update: Update, context: CallbackContext) -> None:
    context.bot_data[update.effective_user]['UM'].current_meeting.archivate_voting()
    update.message.reply_text(context.bot_data[update.effective_user]['UM'].get_info(), parse_mode='HTML')

def voting_list(update: Update, context: CallbackContext) -> None:
    authorized(update, context)
    context.bot_data[update.effective_user]['UM'].get_voting_list()
    list_of_votings = context.bot_data[update.effective_user]['UM'].my_ative_votings

    if len(list_of_votings) == 0:
        update.message.reply_text(f'You have no active invitations on meeting')
        return None

    respond = '<b>You are invited to:</b>\n\n'
    for i, v in enumerate(list_of_votings):
        respond += f'          <pre>[{i}]</pre> meeting <b>"{v.meeting_name}"</b> by <b>{v.user_firstname} ({v.username})</b> with options:'
        for j, m in v.options.items():
            respond += f'\n                    - {m.strftime("%d.%m.%Y %H:%M")}'
        respond += '\n\n'
    keyboard = [[f'/vote {i}' for i in  range(len(list_of_votings))]] + [['/voting_list']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(respond, reply_markup=reply_markup, parse_mode='HTML')
    # context.bot.send_message(chat_id=update.effective_chat.id, text=f'{respond}')

def vote(update: Update, context: CallbackContext) -> None:
    if len(context.args) == 0:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f'Please, type /vote N, where N - is an option number from the list')
        return
    meeting_id = int(context.args[0])
    meeting = context.bot_data[update.effective_user]['UM'].my_ative_votings[meeting_id]
    context.bot_data['meeting_id'] = meeting_id
    """Sends a predefined poll"""
    questions = [t.strftime('%d.%m.%Y %H:%M') for i, t in meeting.options.items()] + ['None above']

    message = context.bot.send_poll(
        update.effective_chat.id,
        f"{meeting.meeting_name}. \nWhat time is appropriate for you?",
        questions,
        is_anonymous=False,
        allows_multiple_answers=True,
    )
    # Save some info about the poll the bot_data for later use in receive_poll_answer
    payload = {
        message.poll.id: {
            "questions": questions,
            "message_id": message.message_id,
            "chat_id": update.effective_chat.id,
            "answers": 0,
            "user": update.effective_user,
            "meeting_id": meeting_id
        }
    }
    # print(payload)
    context.bot_data.update(payload)

def receive_poll_answer(update: Update, context: CallbackContext) -> None:

    answer = update.poll_answer
    poll_id = answer.poll_id
    try:
        questions = context.bot_data[poll_id]["questions"]
        meeting_id = context.bot_data[poll_id]['meeting_id']
    # this means this poll answer update is from an old poll, we can't do our answering then
    except KeyError:
        return
    selected_options = answer.option_ids
    answer_string = ""
    for question_id in selected_options:
        if question_id != selected_options[-1]:
            answer_string += questions[question_id] + " and "
        else:
            answer_string += questions[question_id]

    context.bot_data[update.effective_user]['UM'].vote_done(meeting_id, answer.option_ids)

    context.bot.send_message(
        context.bot_data[poll_id]["chat_id"],
        f"Your choice: {answer_string}! Go to the /voting_list",
        parse_mode=ParseMode.HTML,
    )
    context.bot_data[poll_id]["answers"] += 1
    # Close poll after three participants voted
    if context.bot_data[poll_id]["answers"] == 1:
        context.bot.stop_poll(
            context.bot_data[poll_id]["chat_id"], context.bot_data[poll_id]["message_id"]
        )

def help_command(update: Update, context: CallbackContext) -> None:
    help = f'''
    <b>{update.effective_user.first_name}</b>, by this <b>Meeting Arrangements Bot</b> you could:

    <pre>[1]</pre> Start your first meeting and invite contacts there by /new_meeting

    <pre>[2]</pre> Check your current meeting list and control your meetings /all_my_meetings

    <pre>[3]</pre> Check if you were asked to confirm convenient options for you and vote for appropriate one /voting_list  

    '''
    context.bot.send_message(chat_id=update.effective_chat.id, text=help, parse_mode='HTML')

def hand_typing(update: Update, context: CallbackContext) -> None:
    sub_string = update.message.text
    if context.bot_data[update.effective_user]['command'] == 'new_meeting':
        if len(sub_string) == 0:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=f"You should set the name of meeting: /new_meeting <name>")
            return
        context.bot_data[update.effective_user]['UM'].create_new_meeting(sub_string)
        # context.bot.send_message(chat_id=update.effective_chat.id, text=f"Create meeting '{sub_string}'")
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=context.bot_data[update.effective_user]['UM'].get_info(),
                                 parse_mode='HTML')

    if context.bot_data[update.effective_user]['command'] == 'add_persons':
        args = [arg.replace(',', '') for arg in sub_string.split()]
        invited = context.bot_data[update.effective_user]['UM'].current_meeting.add_persons(args)

        # context.bot.send_message(chat_id=update.effective_chat.id, text=invited)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=context.bot_data[update.effective_user]['UM'].get_info(),
                                 parse_mode='HTML')

    if context.bot_data[update.effective_user]['command'] == 'remove_persons':
        #args = [arg.replace(',', '') for arg in context.args]
        args = [arg.replace(',', '') for arg in sub_string.split(' ')]
        invited = context.bot_data[update.effective_user]['UM'].current_meeting.remove_persons(args)
        # context.bot.send_message(chat_id=update.effective_chat.id, text=invited)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=context.bot_data[update.effective_user]['UM'].get_info(),
                                 parse_mode='HTML')

    if context.bot_data[update.effective_user]['command'] == 'add_options':
        args = {i: datetime.strptime(t, '%d.%m.%Y %H:%M') for i, t in enumerate(sub_string.split(', '))}
        options = context.bot_data[update.effective_user]['UM'].current_meeting.add_options(args)
        # print(f'{args=}')
        # context.bot.send_message(chat_id=update.effective_chat.id, text=options)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=context.bot_data[update.effective_user]['UM'].get_info(),
                                 parse_mode='HTML')

    if context.bot_data[update.effective_user]['command'] == 'remove_options':
        args = {i: datetime.strptime(t, '%d.%m.%Y %H:%M') for i, t in enumerate(sub_string.split(', '))}
        options = context.bot_data[update.effective_user]['UM'].current_meeting.remove_options(args)
        # context.bot.send_message(chat_id=update.effective_chat.id, text=options)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=context.bot_data[update.effective_user]['UM'].get_info(),
                                 parse_mode='HTML')

    if context.bot_data[update.effective_user]['command'] == 'change_duration':
        new_duration = int(sub_string)
        options = context.bot_data[update.effective_user]['UM'].current_meeting.change_duration(new_duration)
        # context.bot.send_message(chat_id=update.effective_chat.id, text=options)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=context.bot_data[update.effective_user]['UM'].get_info(),
                                 parse_mode='HTML')


    context.bot_data[update.effective_user]['command'] = None

def main():

    updater = Updater('5230717894:AAHhisY4pCyYOIUr7MkwwzYPj9TLQ7GUG5s')
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('meeting_info', meeting_info))
    dispatcher.add_handler(CommandHandler('new_meeting', new_meeting))
    dispatcher.add_handler(CommandHandler('help_command', help_command))
    dispatcher.add_handler(CommandHandler('add_persons', add_persons))
    dispatcher.add_handler(CommandHandler('remove_persons', remove_persons))
    dispatcher.add_handler(CommandHandler('add_options', add_options))
    dispatcher.add_handler(CommandHandler('remove_options', remove_options))
    dispatcher.add_handler(CommandHandler('run', run_voting))
    dispatcher.add_handler(CommandHandler('archivate', archivate_voting))
    dispatcher.add_handler(CommandHandler('voting_list', voting_list))
    dispatcher.add_handler(CommandHandler('all_my_meetings', all_my_meetings))
    dispatcher.add_handler(CommandHandler('my_meeting', my_meeting))
    dispatcher.add_handler(CommandHandler('change_duration', change_duration))


    dispatcher.add_handler(CommandHandler('vote', vote))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, hand_typing))
    dispatcher.add_handler(PollAnswerHandler(receive_poll_answer))
    # dispatcher.add_handler(CommandHandler('menu', menu))
    dispatcher.add_handler(CommandHandler("help", help_command))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":

    db.generate_mapping(create_tables=True)

    main()