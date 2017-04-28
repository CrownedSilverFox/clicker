# -*- coding: UTF-8 -*-
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import json

log = ''


class Game:
    def __init__(self):
        self.global_num = None
        self.players = {}
        self.players_logins = {}
        self.players_not_logged = []
        tornado.ioloop.IOLoop.instance().call_later(60, self.save)
        self.load_data()

    def load_data(self):
        with open('data.json') as f:
            data = json.load(f)
            self.players_logins = data["players"]
            self.global_num = data["global_num"]

    def _send_all(self, json, exclude=None):
        for player in self.players:
            if player == exclude:
                continue
            player.write_message(json)

    def received_message(self, player, message):
        global log
        log += json.dumps(message) + '\n'
        if message["key"] == "register":
            self.register(player, message['login'], message['password'])
        if message['key'] == 'login':
            self.login(player, message['login'], message['password'])
        if message['key'] == 'click':
            if not (player in self.players):
                player.write_message(json.dumps({'key': 'error', 'type': 'you are not logged in'}))
                return
            self.global_num += 1*self.players[player]['multiplier']
            self._send_all(json.dumps({'key': 'GN', 'GN': self.global_num}))

    def connect(self, player):
        """
        Подключение игрока
        """
        self.players_not_logged.append(player)
        player.write_message({'key': 'connect', 'message': 'successfully connected'})
        global log
        log += 'player connected\n'

    def disconnect(self, player):
        """
        Отключение игрока
        """
        if player in self.players_not_logged:
            self.players_not_logged.remove(player)
        global log
        log += 'player disconnected\n'

    def save(self):
        with open('data.json', 'w') as f:
            f.write(json.dumps({'players': self.players_logins, 'global_num': self.global_num}))
        tornado.ioloop.IOLoop.instance().call_later(60, self.save)
        with open('log.txt', 'w') as f:
            f.write(log)

    def register(self, player_wsh, login, password):
        self.players_not_logged.remove(player_wsh)
        if login in list(self.players_logins.keys()):
            player_wsh.write_message(json.dumps({'key': 'error', 'type': 'this user already exists'}))
            return
        player = {'login': login, 'password': password, 'clicks': 0, 'multiplier': 1}
        self.players[player_wsh] = player
        self.players_logins[login] = {'password': password, 'clicks': 0, 'multiplier': 1}
        player_wsh.write_message(json.dumps({'key': 'register', 'message': 'successfully registered'}))

    def login(self, player_wsh, login, password):
        if login in list(self.players_logins.keys()) and (self.players_logins[login]['password'] == password):
            self.players[player_wsh] = {'login': login, 'password': password, 'clicks': self.players[login]['clicks'],
                                        'multiplier': self.players[login]['multiplier']}
        player_wsh.write_message(json.dumps({'key': 'login', 'message': 'successfully logged in'}))


class Application(tornado.web.Application):
    def __init__(self):
        self.game = Game()
        handlers = [
            (r'/websocket', WSHandler),
        ]

        tornado.web.Application.__init__(self, handlers)


class WSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        self.application.game.connect(self)

    def on_message(self, message):
        message = json.loads(message, encoding='utf-8')
        print("WSHandler Received message: {}".format(message))
        self.application.game.received_message(self, message)

    def on_close(self):
        if self.application.game.players:
            self.application.game.disconnect(self)

    def check_origin(self, origin):
        return True


application = Application()

if __name__ == "__main__":
    try:
        http_server = tornado.httpserver.HTTPServer(application)
        http_server.listen(8889)
        myIP = socket.gethostbyname(socket.gethostname())
        print('*** Websocket Server Started at %s***' % myIP)
        tornado.ioloop.IOLoop.instance().start()
    except:
        with open('log.txt', 'w') as f:
            f.write(log)
