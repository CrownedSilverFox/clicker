# -*- coding: UTF-8 -*-
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import json
import pymongo

log = ''


class Game:
    def __init__(self):
        """
        Специализированный класс для работы с игровой сессией кликера. 'Мозг' сервера. Примитив, но рабочий.
        """
        self.global_num = None
        self.players = {}
        self.players_not_logged = []
        connection = pymongo.MongoClient()
        self.db = connection.game
        # Через определённый промежуток времени запускает функцию из второго аргумента.
        tornado.ioloop.IOLoop.instance().call_later(600, self.save)

    def _send_all(self, json, exclude=None):
        # рассылка сообщений всем игрокам.
        for player in self.players.keys():
            if player == exclude:
                continue
            player.write_message(json)

    def received_message(self, player, message):
        """
        Реакция на сообщение от игрока. 
        Принимает сообщение формата {"key": "...", ...}
        В зависимости от ключа, реагирует на сообщение и отвечает игроку.
        """
        global log
        log += json.dumps(message) + '\n'
        if message["key"] == "register":
            self.register(player, message['login'])
        if message['key'] == 'login':
            self.login(player, message['login'])
        if message['key'] == 'click':
            if not (player in self.players.keys()):
                player.write_message(json.dumps({'key': 'error', 'type': 'you are not logged in'}))
                return
            self.global_num -= 1*self.players[player]['multiplier']
            self.players[player]['clicks'] += 1*self.players[player]['multiplier']
            player.write_message(json.dumps({'key': 'click', 'GN': self.global_num,
                                             'clicks': self.players[player]['clicks']}))
            self._send_all(json.dumps({'key': 'GN', 'GN': self.global_num}), exclude=player)

    def connect(self, player):
        """
        Подключение игрока
        Принимает WS, добавляет игрока в список подключенных, но не авторизованных.
        Отправляет игроку сообщение, что он успешно подключился.
        """
        self.players_not_logged.append(player)
        player.write_message({'key': 'success', 'type': 'connect'})
        global log
        log += 'player connected\n'

    def disconnect(self, player):
        """
        Отключение игрока
        """
        if player in self.players_not_logged:
            self.players_not_logged.remove(player)
        self.db.players.update({'login': self.players[player]['login']}, {'clicks': self.players[player]['clicks']})
        self.players.pop(player)
        global log
        log += 'player disconnected\n'

    def register(self, player_wsh, login):
        """
        Регистрирует игрока в системе. Если уже есть пользователь с таким логином, возвращает игроку сообщение с ошибкой
        :param player_wsh: WS игрока
        :param login: отправленный с запросом на регистрацию игроком логин.
        """
        self.players_not_logged.remove(player_wsh)
        if self.db.players.find_one({'login': login}) != 'null':
            player_wsh.write_message(json.dumps({'key': 'error', 'type': 'this user already exists'}))
            return
        player = {'login': login, 'clicks': 0, 'multiplier': 1}
        self.players[player_wsh] = player
        player_wsh.write_message(json.dumps({'key': 'success', 'type': 'register', 'GN': self.global_num, 'clicks': 0}))

    def login(self, player_wsh, login):
        """
        Загружает информацию об игроке из БД.
        """
        player = json.dumps(self.db.players.find_one({'login': login}, {'_id': 0}))
        self.players[player_wsh] = player
        player_wsh.write_message(json.dumps({'key': 'success', 'type': 'login', 'GN': self.global_num,
                                             'clicks': self.players[player_wsh]['clicks']}))

    def save(self):
        with open('log.txt', 'w') as f:
            f.write(log)
        for player in self.players.keys():
            self.db.players.update({'login': self.players[player]['login']}, {'clicks': self.players[player]['clicks']})


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
        # на любую ошибку сохраняет логи.
        with open('log.txt', 'w') as f:
            f.write(log)
