from .plugin import Plugin
import os
import json
import csv
from datetime import datetime


class UserNotFoundError(Exception):
    pass


class GroupData:
    def __init__(self, data_dir, message):
        self.data_dir = data_dir
        self.group_id = message.group_id
        self.group_hash = None
        self.users = None
        self.users_changed = False
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup_users()
    
    def get_group_hash(self):
        if self.group_hash is None:
            self.group_hash = '-'.join([str(n) for n in self.group_id])
        return self.group_hash

    def get_users_filename(self):
        return os.path.join(self.data_dir,
                            'users-%s.json' % self.get_group_hash())
     
    def get_users(self):
        if self.users is None:
            try:
                file = open(self.get_users_filename(), 'r')
            except FileNotFoundError:
                return {'closed': False, 'users': {}}
            
            self.users = json.load(file)
        
        return self.users
    
    def get_user_by_name_or_number(self, value):
        users = self.get_users()
        if value in self.users['users']:
            return value, self.users['users'][value]
        
        for number, user in users['users'].items():
            if user['name'] == value:
                return number, user
        
        raise UserNotFoundError()
    
    def set_users(self, users):
        self.users = users
        self.users_changed = True
    
    def cleanup_users(self):
        if self.users_changed:
            with open(self.get_users_filename(), 'w') as file:
                json.dump(self.users, file)
    
    def get_amounts_filename(self):
        return os.path.join(self.data_dir,
                            'amounts-%s.csv' % self.get_group_hash())
    
    def add_cost_data(self, timestamp, amount, note, payer, ratios):
        with open(self.get_amounts_filename(), 'a') as file:
            writer = csv.writer(file)
            writer.writerow([timestamp, amount, note, payer] + ratios)

    def cost_data_generator(self):
        reader = csv.reader(open(self.get_amounts_filename(), 'r'))
        for row in reader:
            ratios = [float(x) for x in row[4:]]
            yield (float(row[0]), float(row[1]), row[2], row[3], ratios)


class Split(Plugin):
    def __init__(self, bot):
        super().__init__(bot)
        self.data_dir = self.bot.args.split_data_dir
        if self.bot.args.split_data_dir is None:
            raise Exception("Please specify split data dir!")
        if not os.path.isdir(self.data_dir):
            raise Exception("split-data-dir does not exist")
    
    def reply(self, reply, attachments=[]):
        super().reply(self.message, reply, attachments)
    
    def error(self, error):
        self.reply(error + ' ❌')
    
    def success(self, message):
        self.reply(message + ' ✔')
    
    def print_help(self):
        self.reply("""HELP
            |  Available line commands:
            |
            |  12.34, [note]
            |  12.34, [note], [user]
            |  12.34, [note], [user], [u:s:e:r=1:2:3:4]
            |  (TODO) 12.34 [currency] etc.
            |
            |  . [text ignored by splitbot]
            |
            |  (TODO) sharesinfo [YYYY-MM] [u:s:e:r=1:2:3:4]
            |
            |  (TODO) preview 12.34
            |  (TODO) preview 12.34, [u:s:e:r=1:2:3:4]
            |
            |  (TODO) convert [currency]
            |  (TODO) convert [amount] [currency]
            |
            |  exportcsv
            |
            |  adduser [name] [number]
            |  adduser [name] myself
            |  listusers
            |  closeusers
            |
            |  help
            |
            |  status""")
    
    def add_user(self, params):
        if len(params) != 2:
            self.error('Need exactly 2 parameters')
            return
        
        users = self.group_data.get_users()
        if users['closed']:
            self.error('Users are closed')
            return
        
        name = params[0]
        # Allow no , : since we split at these later
        if ',' in name or ':' in name:
            self.error('No commas and colons allowed in names')
            return
        
        number = params[1]
        if number == 'myself':
            number = self.message.sender
        
        # Enforce unique name
        for _, user in users['users'].items():
            if name == user['name']:
                self.error('User name already exists')
                return
        
        users['users'][number] = {
            'name': name,
            }
        
        self.group_data.set_users(users)
        self.success('User '+name+' added')
    
    def list_users(self):
        users = self.group_data.get_users()
        
        reply = 'Users'
        if users['closed']:
            reply += ' (closed):\n'
        else:
            reply += ' (open):\n'
        
        for number, user in users['users'].items():
            if users['closed']:
                reply += str(user['pos']) + ' '
            reply += "{name} {number}\n".format(name=user['name'],
                                                number=number)
        
        self.reply(reply)
    
    def close_users(self):
        users = self.group_data.get_users()
        if users['closed']:
            self.error('Users are already closed')
            return
        
        users['closed'] = True
        
        # Assign positions to users
        for pos, number in enumerate(users['users']):
            users['users'][number]['pos'] = pos
        
        self.group_data.set_users(users)
        self.success('Users closed')
    
    def add_cost(self, line):
        params = line.split(',')
        if not len(params):
            self.error('Need at least one parameter')
            return
        
        # Amount
        try:
            amount = float(params[0])
        except ValueError:
            self.error('First paramter must be numeric')
            return
        
        # Note
        note = None
        if len(params) >= 2:
            note = params[1].strip()
        
        users = self.group_data.get_users()
        if not users['closed']:
            self.error('Please close users before adding costs')
            return
        
        # Payer
        payer = self.message.sender
        if len(params) >= 3:
            try:
                payer, _ = self.group_data.get_user_by_name_or_number(
                    params[2].strip())
            except UserNotFoundError:
                self.error('User not found '+params[2].strip())
                return
        
        # Ratios
        ratios = [1 for _ in range(0, len(users['users']))]
        if len(params) >= 4:
            ratios = [0 for _ in range(0, len(users['users']))]
            
            tmp = params[3].strip().split('=')
            if len(tmp) != 2:
                self.error('Ratios must contain exactly one = sign')
                return
            
            values = tmp[1].strip().split(':')
            users = tmp[0].strip().split(':')
            if len(values) != len(users):
                self.error('Users and ratios don\'t occur in same number')
                return
            
            only_zeros = True
            for (value, user) in zip(values, users):
                try:
                    ratio = float(value)
                except ValueError:
                    self.error('{value} is not numeric'.format(value=value))
                    return
                
                if ratio < 0:
                    self.error('{value:f} is negative'.format(value=value))
                    return
                
                if ratio == 0:
                    continue
                
                try:
                    _, user = self.group_data.get_user_by_name_or_number(
                        user.strip())
                except UserNotFoundError:
                    self.error('User {user} not found'.format(user=value))
                    return
                
                only_zeros = False
                ratios[user['pos']] = ratio
            
            if only_zeros:
                self.error('There must be at least one non-zero value in '
                           'ratios')
                return
        
        # Write data
        self.group_data.add_cost_data(self.message.timestamp, amount, note,
                                      payer, ratios)
        
        self.success('Cost added')
    
    def status(self):
        
        users = self.group_data.get_users()
        
        paid_actual = [0 for _ in range(len(users['users']))]
        paid_goal = [0 for _ in range(len(users['users']))]
        
        for (timestamp, amount, note, payer, ratios) in \
                self.group_data.cost_data_generator():
            payer_pos = users['users'][payer]['pos']
            paid_actual[payer_pos] += amount
            
            ratios_sum = sum(ratios)
            for pos, ratio in enumerate(ratios):
                paid_goal[pos] += amount * ratio/ratios_sum
        
        reply = 'Status (actual - goal):\n'
        for _, user in users['users'].items():
            pos = user['pos']
            saldo = paid_actual[pos] - paid_goal[pos]
            
            reply += '{name} {saldo:+.2f}\n'.format(name=user['name'],
                                                    saldo=saldo)
        
        self.reply(reply)
    
    def export_csv(self):
        
        filename = os.path.join(self.data_dir, 'splitbot-export.csv')
        with open(filename, 'w') as file:
            writer = csv.writer(file)
            
            users = self.group_data.get_users()
            
            ratios_header = ['' for user in users['users']]
            for _, user in users['users'].items():
                ratios_header[user['pos']] = user['name']
            writer.writerow(['date', 'amount', 'note', 'payer'] +
                            ratios_header)
            
            for (timestamp, amount, note, payer, ratios) in \
                    self.group_data.cost_data_generator():
                datestr = datetime.fromtimestamp(timestamp/1000.).isoformat()
                writer.writerow([datestr, amount, note,
                                users['users'][payer]['name']] + ratios)
                
        self.reply('Exported CSV is attached', [filename])
        os.remove(filename)
    
    def parse_line(self, line):
        # Ignore empty messages and messages starting with .
        if not len(line) or line[0] == '.':
            return
        
        # Commands
        if line[0].isdigit():
            self.add_cost(line)
            return
        
        params = line.split(' ')
        if params[0] == 'help':
            self.print_help()
        elif params[0] == 'adduser':
            self.add_user(params[1:])
        elif params[0] == 'listusers':
            self.list_users()
        elif params[0] == 'closeusers':
            self.close_users()
        elif params[0] == 'status':
            self.status()
        elif params[0] == 'exportcsv':
            self.export_csv()
        else:
            self.error('Invalid command (or not yet implemented)')
        
    def receive(self, message):
        
        # Only for groups for now
        if message.group_id == []:
            return
        
        # Parse commands line by line
        self.message = message
        with GroupData(self.data_dir, message) as self.group_data:
            for line in message.message.splitlines():
                self.parse_line(line)
        
        # Don't keep message until next one arrives
        self.message = None

__plugin__ = Split
