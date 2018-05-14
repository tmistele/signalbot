from .plugin import Plugin


class PingPong(Plugin):
    def receive(self, message):
        if message.message != 'ping':
            return
        
        self.reply(message, 'pong')

__plugin__ = PingPong
