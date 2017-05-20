# -*- coding: UTF-8 -*-
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import json
import pymongo
from threading import Thread
from datetime import datetime, timedelta
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from base64 import b64decode

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
            'buy_check': self.buy_check
        }
        self.click_types = {
            'factory': 10,
            'human': 1
        }
        self.delta = timedelta(milliseconds=50)
        # Запускает в отдельном потоке работу с БД
        self.updating = tornado.ioloop.PeriodicCallback(self.update, 10000)
        self.updating.start()
        with open('private_key', 'rb') as f:
            self.cipher = PKCS1_v1_5.new(RSA.importKey(f.read()))

    def _send_all(self, json, exclude=None):
        # рассылка сообщений всем игрокам.
        for player in self.players.keys():
            if player == exclude:
                continue
            player.write_message(json)

    def received_message(self, player, message):
        """
        Реакция на сообщение от игрока. 
        Принимает зашифрованное сообщение формата {"key": "...", ...}
        В зависимости от ключа, реагирует на сообщение и отвечает игроку.
        """
        message = self.decrypt(message)
        print('received message: ' + json.dumps(message))
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
        global log
        log += 'player disconnected: %s\n' % self.players[player]['login']
        if player in self.players_not_logged:
            self.players_not_logged.remove(player)
        if player in self.players.keys():
            self.db.players.update({'id': self.players[player]['id']},
                                   {'$set': {'clicks': self.players[player]['clicks'],
                                             'rank_place': self.players[player]['rank_place']}})
            self.players.pop(player)

    def register(self, player_wsh, message):
        """
        Регистрирует игрока в системе. Если уже есть пользователь с таким логином, возвращает игроку сообщение с ошибкой
        :param player_wsh: WS игрока
        :param message: сообщение с данными об игроке
        """
        self.players_not_logged.remove(player_wsh)
        player = {'login': message['login'], 'clicks': 0, 'multiplier': 1,
                  'rank_place': self.db.players.find().count() + 1,
                  'id': message['id'], 'auto_clickers': []}
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
        player_id = message['id']
        if not self.db.players.find_one({'id': player_id}, {'_id': 0}):
            self.register(player_wsh, message)
        player = self.db.players.find_one({'id': player_id}, {'_id': 0})
        self.players[player_wsh] = player
        player_wsh.write_message(json.dumps({'key': 'success', 'type': 'login', 'GN': self.global_num,
                                             'clicks': self.players[player_wsh]['clicks'],
                                             'rank_place': self.players[player_wsh]['rank_place'],
                                             'auto_clickers': self.players[player_wsh]['auto_clickers']}))

    def update(self):
        def work():
            with open('log.txt', 'w') as f:
                f.write(log)
            for player in self.players.keys():
                self.db.players.update({'id': self.players[player]['id']},
                                       {'$set': {'clicks': self.players[player]['clicks'],
                                                 'rank_place': self.players[player]['rank_place'],
                                                 'auto_clickers': self.players[player]['auto_clickers']}})
            clicks_list = list(set([clicks['clicks'] for clicks in self.db.players.find({}, {'clicks': 1, '_id': 0})]))
            clicks_list.sort(reverse=True)
            for num, clicks in enumerate(clicks_list, 1):
                self.db.players.update({'clicks': clicks}, {'$set': {'rank_place': num}})
            for player in self.players.keys():
                self.players[player] = self.db.players.find_one({'id': self.players[player]['id']})
            self.db.gn.update({}, {'$set': {'GN': self.global_num}})
            for player in self.players.keys():
                player.write_message(json.dumps({"key": "rank",
                                                 "rank_place":
                                                     self.db.players.find_one(
                                                         {"id": self.players[player]["id"]})['rank_place']}))
        th = Thread(target=work)
        th.start()

    def on_click(self, player, message):
        if not (player in self.players.keys()):
            player.write_message(json.dumps({'key': 'error', 'type': 'you are not logged in'}))
            return
        if self.players[player].get('time', False):
            if (datetime.now() - self.delta) < (self.players[player]['time']):
                return
        self.players[player]['time'] = datetime.now()
        self.global_num -= 1 * self.players[player]['multiplier']
        self.players[player]['clicks'] += 1 * self.players[player]['multiplier']
        player.write_message(json.dumps({'key': 'click', 'GN': self.global_num,
                                         'clicks': self.players[player]['clicks']}))
        self._send_all(json.dumps({'key': 'GN', 'GN': self.global_num}), exclude=player)

    def bad_key(self, player, *args):
        player.write_message(json.dumps({'key': 'error', 'type': 'bad key'}))

    def buy_check(self, player, message):
        from oauth2client.service_account import ServiceAccountCredentials
        from apiclient.discovery import build
        from apiclient.errors import HttpError
        import httplib2
        package_name, product_id, token = message['packageName'], message['productId'], message['purchaseToken']
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            'client_secret.json',
            ['https://www.googleapis.com/auth/androidpublisher'])

        http = httplib2.Http()
        http = credentials.authorize(http)
        service = build(serviceName="androidpublisher", version="v1.1", http=http)
        try:
            result = service.inapppurchases().get(packageName=package_name,
                                                  productId=product_id, token=token).execute(http=http)
        except HttpError:
            player.write_message(json.dumps({'key': 'buy', 'purchase': 'error'}))
        else:
            player.write_message(json.dumps({'key': 'buy', 'purchase': 'success'}))

    def decrypt(self, message):
        print(message)
        message = b64decode(message)
        err = None
        dec_message = str(self.cipher.decrypt(message, err).decode()).replace(' ', '')
        dec_message = json.loads(dec_message)
        return dec_message


class Application(tornado.web.Application):
    def __init__(self):
        self.game = Game()
        handlers = [
            (r'/websocket', PlayersHandler),
        ]

        tornado.web.Application.__init__(self, handlers)


class PlayersHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        self.application.game.connect(self)

    def on_message(self, message):
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
