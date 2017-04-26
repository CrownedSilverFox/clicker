# -*- coding: UTF-8 -*-
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import json
import time
from settings import *


class Game:
    def __init__(self):
        self._state = REGISTER  # статус хода
        self._turn = 0  # индекс команды, чей сейчас ход
        self.teams = []  # список команд
        self._checked_teams = 0
        self.points = [0, 0, 0, 0]
        self.do = {
            REGISTER: lambda: None,
            SELECT_QUESTION: self.select_question,
            SELECT_ANSWER: self.select_answer,
            SET_MARKERS: self.send_matrix
        }
        self.questions = None
        self.answers = None
        self.question = None
        self.time_end = 30
        self.desk_matrix = []
        self.load_data()

    def load_data(self):
        with open(os.path.join("data", "questions.json")) as f:
            self.questions = json.load(f)
        with open(os.path.join("data", "right_answers.json")) as f:
            self.answers = json.load(f)
        # Генерация стартовой матрицы поля
        if len(TEAM_COLORS) == 4:
            self.desk_matrix = list([list([MARKERS[TEAM_COLORS[(j // (DESK_SIZE // 2)) +
                                                               (2 if i >= DESK_SIZE/2 else 0)]]
                                           for j in range(0, DESK_SIZE)]) for i in range(0, DESK_SIZE)])
        else:
            raise ValueError('Команд доложно быть 4')

    def _send_all(self, json, exclude=None):
        for team in self.teams:
            if team == exclude:
                continue
            team.write_message(json)

    def received_message(self, team, message):
        if not self.teams:
            return
        if message["key"] == "quest_sel":
            self._send_all(json.dumps({'key': 'question', 'question': self.chosen_quest(int(message['id']))}))
            self.state += 1
        if message['key'] == 'answer_checked':
            self.answering(message, team)
        if message['key'] == 'mark':
            self.mark(message, team)

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if value > MAX_STATE:
            self._state = 1
            self.turn += 1
        else:
            self._state = value

        self.do[self.state]()

    @property
    def turn(self):
        return self._turn

    @turn.setter
    def turn(self, value):
        self._turn = value
        if value == len(self.teams):
            self._turn = 0

    def connect(self, team):
        """
        Подключение команды
        """
        # TODO: добавить восстановление подключения команды
        if self.state != REGISTER:
            raise ValueError("Game in progress, registration is closed")

        self.teams.append(team)
        # Отправка цвета команды
        team.write_message({'key': 'color', 'color': TEAM_COLORS[self.teams.index(team)]})
        if len(TEAM_COLORS[:2]) == len(self.teams):
            self.state += 1
            self._send_all({"key": "register", "register_closed": True})
            return

        # Сообщения для индикатора подключения команд
        self._send_all({"key": "register", "connected_teams": [team.color for team in self.teams]})

    def disconnect(self, team):
        """
        Отключение команды
        """
        self.teams.remove(team)
        if self._state == REGISTER:
            self._send_all({"key": "register", "connected_teams": [team.color for team in self.teams]})
        if not self.teams:
            self.state = REGISTER
            self.reload()

    def select_question(self):
        questions = self.questions.copy()
        if self.questions:
            for key in self.questions.keys():
                if not questions[key]:
                    questions.pop(key)
        self.questions = questions
        if not self.questions:
            self.game_end()
            return
        # Всем командам отсылаем вопросы
        self._send_all({"key": "questions", "questions": self.questions})
        # Текущей команде(чей сейчас ход) отсылаем сообщение "Выберите вопрос"
        self.teams[self.turn].write_message({"key": "quest_sel"})

    def select_answer(self):
        for second in range(1, self.time_end+1)[::-1]:
            message = {'key': 'time', 'time': second}
            self._send_all(json.dumps(message))
            time.sleep(1)
        message = {'key': 'time_up'}
        self._send_all(json.dumps(message))

    def chosen_quest(self, id):
        for group in self.questions.keys():
                for num, quest in enumerate(self.questions[group]):
                    if quest['id'] == id:
                        self.questions[group].pop(num)
                        self.question = quest
                        return quest

    def check_answer(self, answer):
        for quest in self.answers:
            if quest['id'] == self.question['id']:
                return answer == quest['answer']

    @property
    def marks(self):
        points = {'RED': 0, 'GREEN': 0, 'BLUE': 0, 'YELLOW': 0}
        for line in self.desk_matrix:
            for color in MARKERS.keys():
                points[color] += line.count(MARKERS[color])
        return points

    def mark(self, message, team):
        if self.points[self.teams.index(team)] and (self.desk_matrix[int(message['i'])][int(message['j'])] !=
                                                        MARKERS[TEAM_COLORS[self.teams.index(team)]]):
            self.desk_matrix[int(message['i'])][int(message['j'])] = MARKERS[TEAM_COLORS[self.teams.index(team)]]
            self._send_all(json.dumps({'key': 'mark', 'i': int(message['i']), 'j': int(message['j']),
                                       'image': MARKERS[TEAM_COLORS[self.teams.index(team)]]}))
            self.points[self.teams.index(team)] -= 1
            team.write_message(json.dumps({'key': 'points', 'points': self.points[self.teams.index(team)]}))
        self._send_all(json.dumps({'key': 'marks', 'marks': self.marks, 'teams': TEAM_COLORS[:]}))
        if (self.points == [0, 0, 0, 0]) and (self.state == 3):
            self.state += 1

    @property
    def checked_teams(self):
        return self._checked_teams

    @checked_teams.setter
    def checked_teams(self, value):
        self._checked_teams = value
        if value == len(self.teams):
            self._checked_teams = -1

    def answering(self, message, team):
        self.checked_teams += 1
        if self.check_answer(message['checkedAnswer']):
            team.write_message(json.dumps({'key': 'points', 'points': self.question['cost']}))
            self.points[self.teams.index(team)] = int(self.question['cost'])
        else:
            team.write_message(json.dumps({'key': 'points', 'points': 0}))
        if self.checked_teams == -1:
            self.checked_teams = 0
            self.state += 1

    def send_matrix(self):
        self._send_all(json.dumps({'key': 'marks', 'marks': self.marks, 'teams': TEAM_COLORS[:]}))
        self._send_all(json.dumps({'key': 'matrix', 'matrix': self.desk_matrix}))

    def game_end(self):
        marks = self.marks
        winner = TEAM_COLORS[0]
        for team in marks.keys():
            if marks[winner] < marks[team]:
                winner = team
        self._send_all(json.dumps({'key': 'end', 'marks': self.marks,
                                   'teams': TEAM_COLORS[:], 'winner': winner}))
        # Случайно реализовал возможность сыграть повторно.
        time.sleep(5)
        self.reload()

    def reload(self):
        self.load_data()
        self.__init__()


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
        print("client connect", self.color)

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
