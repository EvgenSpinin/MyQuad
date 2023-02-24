# В ЄТОЙ ВЕРСИИ ПІТАЮСЬ СДЕЛАТЬ ЗАХВАТ ОБЬЕКТА И ОПРЕДЕЛЕНИЕ ПО ЕГО КОНТУРАМ

from flask import Flask, render_template, Response, request
import cv2
import serial
import threading
import time
import json
import argparse
from yamspy import MSPy
import curses
from collections import deque
from itertools import cycle


app = Flask(__name__)
camera = cv2.VideoCapture(0)  # веб камера

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)   # Определенные разрешения с некоторыми камерами могут не работать, поэтому для
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)  # уменьшения разрешения можно также использовать resize в методе getFramesGenerator

fixcont = False
controlX, controlY = 0.0, 0.0  # глобальные переменные вектора движения робота. Диапазоны: [-1, 1]
alt = 1
bat = 2
mode = 3
kinemat = 4
var = 5
text = "OK"

#Переменніе для цикличного получения жанніх с полетника
CTRL_LOOP_TIME = 1/100
SLOW_MSGS_LOOP_TIME = 1/5 # these messages take a lot of time slowing down the loop...
NO_OF_CYCLES_AVERAGE_GUI_TIME = 10

serial_port = "/dev/ttyS0"

def getFramesGenerator():
    """ Генератор фреймов для вывода в веб-страницу, тут же можно поиграть с openCV"""
    global bat, alt, pithc, roll, yaw, alt2, RCx, RCyaw, RCtrotle, RCpitch, RCroll
    fixcont = 0
    global controlX, controlY
    while True:




        # time.sleep(0.01)  # ограничение fps (если видео тупит, можно убрать)

        iSee = False  # флаг: был ли найден контур

        success, frame = camera.read()  # Получаем фрейм с камеры

        if success:
            frame = cv2.rotate(frame , cv2.ROTATE_180)
            frame = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)  # уменьшаем разрешение кадров (если
            # видео тупит, можно уменьшить еще больше)
            height, width = frame.shape[0:2]  # получаем разрешение кадра

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)  # переводим кадр из RGB в HSV
            #binary = cv2.inRange(hsv, (18, 60, 100), (32, 255, 255))  # пороговая обработка кадра (выделяем все желтое)
            #binary = cv2.inRange(hsv, (0, 0, 0), (255, 255, 35))  # пороговая обработка кадра (выделяем все черное)
            binary = cv2.inRange(hsv, (0, 0, 200), (180, 50, 255))  # пороговая обработка кадра (выделяем все белое)
            #binary = cv2.inRange(hsv, (100, 50, 50), (140, 255, 255))  # пороговая обработка кадра (выделяем все синее)
            #binary = cv2.inRange(hsv, (45, 100, 50), (75, 255, 255))  # пороговая обработка кадра (выделяем все зеленое)

            # Преобразуем кадр в оттенки серого
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            """
            # Чтобы выделить все красное необходимо произвести две пороговые обработки, т.к. тон красного цвета в hsv
            # находится в начале и конце диапазона hue: [0; 180), а в openCV, хз почему, этот диапазон не закольцован.
            # поэтому выделяем красный цвет с одного и другого конца, а потом просто складываем обе битовые маски вместе

            bin1 = cv2.inRange(hsv, (0, 60, 70), (10, 255, 255)) # красный цвет с одного конца
            bin2 = cv2.inRange(hsv, (160, 60, 70), (179, 255, 255)) # красный цвет с другого конца
            binary = bin1 + bin2  # складываем битовые маски
            """

            #если хотим ловить по серому то коментируем , если по цветному , то коментируем ниже
            #contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)  # получаем контуры выделенных областей


            _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)



            if len(contours) != 0:  # если найден хоть один контур

                #if fixcont == 
                maxc = max(contours, key=cv2.contourArea)  # находим наибольший контур
                #fixcont = True    # фиксируем в переменную
                #else:
                #      maxc = maxc

                # еслинажать на кнопку , фиксируем максимальній контур в зафиксированій и переводим переменную
                # в режим зафиксировано
                if RCx > 1700:
                   best_contour = maxc
                   fixcont = 1
 
                if fixcont == 1:    #если біла фиксация контура
                    # Находим контур объекта, который наиболее похож на первый контур
                    best_match = None
                    min_diff = float('inf')
                    for contour in contours:
                        diff = cv2.matchShapes(best_contour, contour, cv2.CONTOURS_MATCH_I2, 0)
                        if diff < min_diff:
                           min_diff = diff
                           best_match = contour

                     # Проверяем, что найденный контур достаточно похож на первый контур
                    if min_diff < 0.2:
                      # Фиксируем объект на этом кадре
                         best_contour = best_match
                         x, y, w, h = cv2.boundingRect(best_contour)
                         cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)


                moments = cv2.moments(maxc)  # получаем моменты этого контура
                """
                # moments["m00"] - нулевой момент соответствует площади контура в пикселях,
                # поэтому, если в битовой маске присутствуют шумы, можно вместо
                # if moments["m00"] != 0:  # использовать

                if moments["m00"] > 20: # тогда контуры с площадью меньше 20 пикселей не будут учитываться
                   """
                if moments["m00"] > 20:  # контуры с площадью меньше 20 пикселей не будут учитываться
                   cx = int(moments["m10"] / moments["m00"])  # находим координаты центра контура по x
                   cy = int(moments["m01"] / moments["m00"])  # находим координаты центра контура по y

                   iSee = True  # устанавливаем флаг, что контур найден

                   controlX = 2 * (cx - width / 2) / width  # находим отклонение найденного объекта от центра кадра и
                   controlY = 2 * (cy - height / 2) / height  # находим отклонение найденного объекта от центра кадра и
                       # нормализуем его (приводим к диапазону [-1; 1])

                   cv2.drawContours(frame, maxc, -1, (0, 255, 0), 1)  # рисуем контур
                   cv2.line(frame, (cx, 0), (cx, height), (0, 255, 0), 1)  # рисуем линию линию по x
                   cv2.line(frame, (0, cy), (width, cy), (0, 255, 0), 1)  # линия по y
                   cv2.drawContours(frame, best_match, -1, (0, 255, 0), 1)  # рисуем  зафиксированій контур



            if iSee:    # если был найден объект
                #controlY = 0.5  # начинаем ехать вперед с 50% мощностью
                controlY = controlY
            else:
                controlY = 0.0  # останавливаемся
                controlX = 0.0  # сбрасываем меру поворота
                fixcont = False

            miniBin = cv2.resize(binary, (int(binary.shape[1] / 4), int(binary.shape[0] / 4)),  # накладываем поверх
                                 interpolation=cv2.INTER_AREA)                                  # кадра маленькую

            miniBin = cv2.cvtColor(miniBin, cv2.COLOR_GRAY2BGR)                                 # битовую маску
            frame[-2 - miniBin.shape[0]:-2, 2:2 + miniBin.shape[1]] = miniBin             # для наглядности

            cv2.putText(frame, 'iSee: {};'.format(iSee), (width - 160, height - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'controlY: {:.2f}'.format(controlY), (width - 280, height - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'controlX: {:.2f}'.format(controlX), (width - 80, height - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'bat: {:.2f}'.format(bat), (width - 70, height - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'alt: {:.2f}'.format(alt), (width - 70, height - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'RCx: {}'.format(RCx), (width - 70, height - 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'RCyaw: {}'.format(RCyaw), (width - 70, height - 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'RCtrotle: {}'.format(RCtrotle), (width - 70, height - 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'RCpitch: {}'.format(RCpitch), (width - 70, height - 140),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'RCroll: {}'.format(RCroll), (width - 70, height - 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'mot: {}'.format(var), (width - 240, height - 170),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (5, 5, 5), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'text: {}'.format(text), (width - 70, height - 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.23, (170, 50, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст


            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/video_feed')




def video_feed():
    """ Генерируем и отправляем изображения с камеры"""
    return Response(getFramesGenerator(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/')
def index():
    """ Крутим html страницу """
    return render_template('index.html')


if __name__ == '__main__':
    # пакет, посылаемый на ардуинку
    msg = {
        "speedA": 0,  # в пакете посылается скорость на левый и правый борт тележки
        "speedB": 0  #
    }

    # параметры робота
    speedScale = 0.60  # определяет скорость в процентах (0.60 = 60%) от максимальной абсолютной
    maxAbsSpeed = 100  # максимальное абсолютное отправляемое значение скорости
    sendFreq = 5  # слать 5 пакетов в секунду

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=5000, help="Running port")
    parser.add_argument("-i", "--ip", type=str, default='192.168.0.108', help="Ip address")
    parser.add_argument('-s', '--serial', type=str, default='/dev/ttyUSB0', help="Serial port")
    args = parser.parse_args()

#---------------------------------------------------------------------------

    def loadMSPr():
        """ функция цикличного приема ПАКЕТА данніх с полетника """

        global bat, alt, mode, kinemat, var, RCx, RCyaw, RCtrotle, RCpitch, RCroll  
        CMDS = {
                'roll':     1500,
                'pitch':    1500,
                'throttle': 900,
                'yaw':      1500
                }
        CMDS_ORDER = ['roll', 'pitch', 'throttle', 'yaw']

        with MSPy(device=serial_port, loglevel='DEBUG', baudrate=115200) as board:

            average_cycle = deque([0]*NO_OF_CYCLES_AVERAGE_GUI_TIME)
            slow_msgs = cycle(['MSP_ANALOG', 'MSP_STATUS_EX', 'MSP_MOTOR', 'MSP_RC', 'MSP_ALTITUDE'])
            cursor_msg = ""
            last_loop_time = last_slow_msg_time = last_cycleTime = time.time()

            while True:
                    start_time = time.time()

                    CMDS['throttle'] = 1500
            
                    CMDS['yaw'] = 1500
                
                    CMDS['roll'] = 1500

                    CMDS['pitch'] = 1500

                    if (time.time()-last_loop_time) >= CTRL_LOOP_TIME:
                        last_loop_time = time.time()
                        # Send the RC channel values to the FC
                        if board.send_RAW_RC([CMDS[ki] for ki in CMDS_ORDER]):
                            dataHandler = board.receive_msg()
                            board.process_recv_data(dataHandler)

 





                    if (time.time()-last_slow_msg_time) >= SLOW_MSGS_LOOP_TIME:
                        last_slow_msg_time = time.time()
                        next_msg = next(slow_msgs) # circular list

                        if board.send_RAW_msg(MSPy.MSPCodes[next_msg], data=[]):
                            dataHandler = board.receive_msg()
                            board.process_recv_data(dataHandler)

                        if next_msg == 'MSP_ANALOG':
                            #print(board.process_mode(board.CONFIG['mode']))
                            #print("Flight Mode: {}".format(board.process_mode(board.CONFIG['mode'])))
                            bat = board.ANALOG['voltage']

                        elif next_msg == 'MSP_STATUS_EX':
                            #print(board.process_mode(board.CONFIG['mode']))
                            print("Flight Mode: {}".format(board.process_mode(board.CONFIG['mode'])))

                        elif next_msg == 'MSP_MOTOR':
                            var = board.MOTOR_DATA

                        elif next_msg == 'MSP_RC':
                            msgRC = board.RC['channels']
                            #msgRctest = [0, 1, 2, 3, 4, 5, 6, 7]
                            #print(msgRc[3])
                            RCx = msgRC[10]
                            RCyaw=msgRC[2]
                            RCtrotle=msgRC[3]
                            RCpitch=msgRC[1]
                            RCroll=msgRC[0]
                            #print (RCx)
 
                        elif next_msg == 'MSP_ALTITUDE':
                            #print(board.SENSOR_DATA['kinematics'])
                            alt = board.SENSOR_DATA['altitude']
                            kinemat = 777
                    end_time = time.time()
                    last_cycleTime = end_time-start_time

#                    print(next_msg)



    threading.Thread(target=loadMSPr, daemon=True).start()    # запускаем тред по приему данніх с полетника

#-----------------------------------------------------------------------------------------------------------


    app.run(debug=False, host=args.ip, port=args.port)   # запускаем flask приложение

