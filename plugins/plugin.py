class Plugin:
    def __init__(self, bot):
        self.bot = bot
    
    def receive(self, message):
        pass
    
    def reply(self, message, reply, attachments=[]):
        if message.group_id != []:
            self.bot.signal.sendGroupMessage(reply, attachments, message.group_id)
        else:
            self.bot.signal.sendMessage(reply, attachments, [message.sender])
