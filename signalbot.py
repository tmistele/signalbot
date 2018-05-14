import argparse
import importlib
from pydbus import SessionBus, SystemBus, connect
from gi.repository import GLib


class Message:
    def __init__(self, timestamp, sender, group_id, message, attachments):
        self.timestamp = timestamp
        self.sender = sender
        self.group_id = group_id
        self.message = message
        self.attachments = attachments


class Bot:
    def __init__(self, args):
        self.args = args
        self.plugins = []
    
    def receive(self, timestamp, sender, group_id, message, attachments):
        message = Message(timestamp, sender, group_id, message, attachments)
        for plugin in self.plugins:
            plugin.receive(message)
    
    def start(self):
        
        # Load requested plugins
        self.plugins = [
            importlib.import_module('plugins.'+plugin).__plugin__(self)
            for plugin in self.args.plugins]
        
        # Start listening for messages
        if self.args.bus == 'session' or self.args.bus is None:
            bus = SessionBus()
        elif self.args.bus == 'system':
            bus = SystemBus()
        else:
            bus = connect(self.args.bus)
        
        self.signal = bus.get('org.asamk.Signal')
        self.signal.onMessageReceived = self.receive
        
        loop = GLib.MainLoop()
        loop.run()


if __name__ == '__main__':
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Signal Bot')
    parser.add_argument('--bus', help='DBus bus type (system, session) or bus '
                                      'address')
    parser.add_argument('plugins', nargs='+', metavar='plugin')
    
    plugin_group = parser.add_argument_group('plugin arguments')
    plugin_group.add_argument('--split-data-dir', help='Data directory for '
                                                       'split plugin')
    
    args = parser.parse_args()
    
    # Start bot
    bot = Bot(args)
    bot.start()
