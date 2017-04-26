# -*- coding: UTF-8 -*-
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import json


class Game:
    def __init__(self):
        self.global_num = None
        self.players = {}
        tornado.ioloop.IOLoop.instance().call_later(60, self.save)

    def load_data(self):
        with open('data') as f:
            data = json.load(f)
            self.players = data["players"]
            self.global_num = data["global_num"]

    def _send_all(self, json, exclude=None):
        for player in self.players:
            if player == exclude:
                continue
            player.write_message(json)

    def received_message(self, team, message):
        if message["key"] == "register":

        if message['key'] == 'click':
            self.answering(message, team)

    def connect(self, player):
        """
        Подключение игрока
        """
        self.players.append(player)
        # Отправка цвета команды
        team.write_message({'key': 'global_num', 'num': self.global_num})

    def disconnect(self, team):
        """
        Отключение игрока
        """
        self.players.remove(team)
        if self._state == REGISTER:
            self._send_all({"key": "register", "connected_teams": [team.color for team in self.players]})
        if not self.players:
            self.state = REGISTER
            self.reload()

    def save(self):
        pass


class Team:
    team_colors = TEAM_COLORS[:2]

    def __init__(self):
        if not self.team_colors:
            raise ValueError("Game Full")
        self.color = self.team_colors.pop(0)

    def on_delete(self):
        self.team_colors.insert(0, self.color)

    def __repr__(self):
        return "Team {}".format(self.color)


class Application(tornado.web.Application):
    def __init__(self):
        self.game = Game()
        handlers = [
            (r'/websocket', WSHandler),
        ]

        tornado.web.Application.__init__(self, handlers)


class WSHandler(tornado.websocket.WebSocketHandler, Team):
    def open(self):
        self.application.game.connect(self)

    def on_message(self, message):
        message = json.loads(message, encoding='utf-8')
        print("WSHandler Received message: {}".format(message))
        self.application.game.received_message(self, message)

    def on_close(self):
        print("close connection", self)
        if self.application.game.teams:
            self.application.game.disconnect(self)
        self.on_delete()

    def check_origin(self, origin):
        return True


application = Application()

if __name__ == "__main__":
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8889)
    myIP = socket.gethostbyname(socket.gethostname())
    print('*** Websocket Server Started at %s***' % myIP)
    tornado.ioloop.IOLoop.instance().start()
