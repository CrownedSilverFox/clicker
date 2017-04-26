import os
TEAM_COLORS = ["RED", "GREEN", "BLUE", "YELLOW"]
# Фазы(state) игры
REGISTER = 0
SELECT_QUESTION = 1
SELECT_ANSWER = 2
SET_MARKERS = 3
# TODO: не забывать изменять максимальный статус, при добавленни новых фаз
MAX_STATE = SET_MARKERS  # Всегда равна максимальному статусу
DESK_SIZE = 10
IMAGES_PATH = os.path.join('static/images')
MARKERS = {
    'RED': os.path.join(IMAGES_PATH, 'RED.png'),
    'BLUE': os.path.join(IMAGES_PATH, 'BLUE.png'),
    'GREEN': os.path.join(IMAGES_PATH, 'GREEN.png'),
    'YELLOW': os.path.join(IMAGES_PATH, 'YELLOW.png')
}
