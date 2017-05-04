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
        connection = pymongo.MongoClient()
        self.db = connection.game
        self.global_num = self.db.gn.find_one({}, {'_id': 0})['GN']
        self.players = {}
        self.players_not_logged = []
        self.messages = {
            'login': self.login,
            'click': self.on_click,
            'register': self.register
        }
        self.click_types = {
            'factory': 10,
            'human': 1
        }
        # Через определённый промежуток времени запускает функцию из второго аргумента.
        tornado.ioloop.IOLoop.instance().call_later(60, self.save)

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
        log += 'received message: ' + json.dumps(message) + '\n'
        self.messages.get(message['key'], self.bad_key)(player, message)

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
        if player in self.players.keys():
            self.db.players.update({'login': self.players[player]['login']},
                                   {'$set':  {'clicks': self.players[player]['clicks'],
                                              'rank_place': self.players[player]['rank_place']}})
            self.players.pop(player)
        global log
        log += 'player disconnected\n'

    def register(self, player_wsh, message):
        """
        Регистрирует игрока в системе. Если уже есть пользователь с таким логином, возвращает игроку сообщение с ошибкой
        :param player_wsh: WS игрока
        :param message: сообщение с данными об игроке
        """
        if self.db.players.find_one({'mail': message['mail']}):
            player_wsh.write_message(json.dumps({'key': 'error', 'type': 'user already exists'}))
        self.players_not_logged.remove(player_wsh)
        player = {'login': message['login'], 'clicks': 0, 'multiplier': 1,
                  'rank_place': self.db.players.find().count() + 1,
                  'mail': message['mail'], 'auto_clickers': []}
        self.players[player_wsh] = player
        self.db.players.insert_one(player)
        player_wsh.write_message(json.dumps({'key': 'success', 'type': 'register', 'GN': self.global_num, 'clicks': 0,
                                             'rank_place': self.players[player_wsh]['rank_place'],
                                             'auto_clickers': []}))

    def login(self, player_wsh, message):
        """
        Загружает информацию об игроке из БД.
        Если его там нет, регистрирует.
        """
        mail = message['mail']
        if not self.db.players.find_one({'mail': mail}, {'_id': 0}):
            player_wsh.write_message(json.dumps({'key': 'error', 'type': 'you are not registered'}))
        player = self.db.players.find_one({'mail': mail}, {'_id': 0})
        self.players[player_wsh] = player
        player_wsh.write_message(json.dumps({'key': 'success', 'type': 'login', 'GN': self.global_num,
                                             'clicks': self.players[player_wsh]['clicks'],
                                             'login': self.players[player_wsh]['login'],
                                             'auto_clickers': self.players[player_wsh]['auto_clickers']}))

    def save(self):
        with open('log.txt', 'w') as f:
            f.write(log)
        for player in self.players.keys():
            self.db.players.update({'login': self.players[player]['login']},
                                   {'$set': {'clicks': self.players[player]['clicks'],
                                             'rank_place': self.players[player]['rank_place'],
                                             'auto_clickers': self.players[player]['auto_clickers']}})
        self.db.gn.update({}, {'$set': {'GN': self.global_num}})
        tornado.ioloop.IOLoop.instance().call_later(60, self.save)

    def on_click(self, player, message):
        if not (player in self.players.keys()):
            player.write_message(json.dumps({'key': 'error', 'type': 'you are not logged in'}))
            return
        self.global_num -= self.click_types[message['type']] * self.players[player]['multiplier']
        self.players[player]['clicks'] += self.click_types[message['type']] * self.players[player]['multiplier']
        if '"rank_place": %s' % self.players[player]['rank_place'] in self.players.items().__repr__():
            for player_wsh in self.players.keys():
                if (self.players[player_wsh]['rank_place'] - 1) == self.players[player]['rank_place']:
                    self.players[player_wsh]['rank_place'] += 1
                    self.players[player]['rank_place'] -= 1
                    player_wsh.write_message(json.dumps({'key': 'click', 'GN': self.global_num,
                                                         'clicks': self.players[player_wsh]['clicks'],
                                                         'rank_place': self.players[player_wsh]['rank_place']}))
                    break
        elif (self.db.players.find_one({'rank_place': self.players[player]['rank_place'] - 1})) \
                and self.players[player]['clicks'] > self.db.players.find_one(
                    {'rank_place': self.players[player]['rank_place'] - 1})['clicks']:
            self.db.players.update(
                {'rank_place': self.players[player]['rank_place'] - 1},
                {'$set': {'rank_place': self.players[player]['rank_place']}})
            self.players[player]['rank_place'] -= 1
        player.write_message(json.dumps({'key': 'click', 'GN': self.global_num,
                                         'clicks': self.players[player]['clicks'],
                                         'rank_place': self.players[player]['rank_place']}))
        self._send_all(json.dumps({'key': 'GN', 'GN': self.global_num}), exclude=player)

    def bad_key(self, player, *args):
        player.write_message(json.dumps({'key': 'error', 'type': 'bad key'}))


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
