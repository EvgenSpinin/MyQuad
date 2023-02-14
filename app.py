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
    global bat, alt, pithc, roll, yaw, alt2
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
            binary = cv2.inRange(hsv, (0, 0, 0), (255, 255, 35))  # пороговая обработка кадра (выделяем все черное)
            #binary = cv2.inRange(hsv, (0, 0, 0), (0, 0, 255))  # пороговая обработка кадра (выделяем все белое)

            """
            # Чтобы выделить все красное необходимо произвести две пороговые обработки, т.к. тон красного цвета в hsv
            # находится в начале и конце диапазона hue: [0; 180), а в openCV, хз почему, этот диапазон не закольцован.
            # поэтому выделяем красный цвет с одного и другого конца, а потом просто складываем обе битовые маски вместе

            bin1 = cv2.inRange(hsv, (0, 60, 70), (10, 255, 255)) # красный цвет с одного конца
            bin2 = cv2.inRange(hsv, (160, 60, 70), (179, 255, 255)) # красный цвет с другого конца
            binary = bin1 + bin2  # складываем битовые маски
            """

            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_NONE)  # получаем контуры выделенных областей

            if len(contours) != 0:  # если найден хоть один контур
                maxc = max(contours, key=cv2.contourArea)  # находим наибольший контур
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
                    # нормализуем его (приводим к диапазону [-1; 1])

                    cv2.drawContours(frame, maxc, -1, (0, 255, 0), 1)  # рисуем контур
                    cv2.line(frame, (cx, 0), (cx, height), (0, 255, 0), 1)  # рисуем линию линию по x
                    cv2.line(frame, (0, cy), (width, cy), (0, 255, 0), 1)  # линия по y

            if iSee:    # если был найден объект
                controlY = 0.5  # начинаем ехать вперед с 50% мощностью
            else:
                controlY = 0.0  # останавливаемся
                controlX = 0.0  # сбрасываем меру поворота

            miniBin = cv2.resize(binary, (int(binary.shape[1] / 4), int(binary.shape[0] / 4)),  # накладываем поверх
                                 interpolation=cv2.INTER_AREA)                                  # кадра маленькую

            miniBin = cv2.cvtColor(miniBin, cv2.COLOR_GRAY2BGR)                                 # битовую маску
            frame[-2 - miniBin.shape[0]:-2, 2:2 + miniBin.shape[1]] = miniBin             # для наглядности

            cv2.putText(frame, 'iSee: {};'.format(iSee), (width - 160, height - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'controlX: {:.2f}'.format(controlX), (width - 80, height - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'bat: {:.2f}'.format(bat), (width - 70, height - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'alt: {:.2f}'.format(alt), (width - 70, height - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

#            cv2.putText(frame, 'mode: {:.2f}'.format(mode), (width - 70, height - 60),
#                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

#            cv2.putText(frame, 'kin: {:.2f}'.format(kinemat), (width - 70, height - 80),
#                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'mot: {}'.format(var), (width - 240, height - 170),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (5, 5, 5), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            cv2.putText(frame, 'text: {}'.format(text), (width - 70, height - 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.23, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст


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


    #serialPort = serial.Serial(args.serial, 9600)   # открываем uart

    def sender():
        """ функция цикличной отправки пакетов по uart """
        global controlX, controlY
        while True:
            speedA = maxAbsSpeed * (controlY + controlX)    # преобразуем скорость робота,
            speedB = maxAbsSpeed * (controlY - controlX)    # в зависимости от положения джойстика

            speedA = max(-maxAbsSpeed, min(speedA, maxAbsSpeed))    # функция аналогичная constrain в arduino
            speedB = max(-maxAbsSpeed, min(speedB, maxAbsSpeed))    # функция аналогичная constrain в arduino

            msg["speedA"], msg["speedB"] = speedScale * speedA, speedScale * speedB     # урезаем скорость и упаковываем

            serialPort.write(json.dumps(msg, ensure_ascii=False).encode("utf8"))  # отправляем пакет в виде json файла
            time.sleep(1 / sendFreq)

   # threading.Thread(target=sender, daemon=True).start()    # запускаем тред отправки пакетов по uart с демоном

#---------------------------------------------------------------------------------------------

    def loader():
        """ функция цикличного приема JSON """
        global controlX, control
        global bat, alt, mode, kinemat, var
        while True:
            with open('data.json', 'r') as f:
                data = f.read()
                json_data = json.loads(data)
                bat = json_data['bat']
                alt = json_data['alt']
                mode = json_data['mode']
                kinemat = json_data['kinemat']
                var = json_data['var']

            time.sleep(1 / sendFreq)
#            print(roll)
#    threading.Thread(target=loader, daemon=True).start()    # запускаем тред приема данніх с фаила JSON

#---------------------------------------------------------------------------------------------------
    def loadMSP():
        """ функция цикличного приема данніх с полетника """
        global controlX, control
        global bat, alt, mode, kinemat, var
        with MSPy(device='/dev/ttyS0', loglevel='DEBUG', baudrate=115200) as board:

            while True:

                    if board.send_RAW_msg(MSPy.MSPCodes['MSP_ALTITUDE'], data=[]):

                       dataHandler = board.receive_msg()
                       board.process_recv_data(dataHandler)
                       print(board.SENSOR_DATA['altitude'])
                       alt2=board.SENSOR_DATA['altitude']

                    time.sleep(1 / sendFreq)

#    threading.Thread(target=loadMSP, daemon=True).start()    # запускаем тред по приему данніх с полетника

#--------------------------------------------------------------------------------------------------------

    def loadMSPr():
        """ функция цикличного приема ПАКЕТА данніх с полетника """

        global bat, alt, mode, kinemat, var

        with MSPy(device=serial_port, loglevel='DEBUG', baudrate=115200) as board:

            average_cycle = deque([0]*NO_OF_CYCLES_AVERAGE_GUI_TIME)
            slow_msgs = cycle(['MSP_ANALOG', 'MSP_STATUS_EX', 'MSP_MOTOR', 'MSP_RC', 'MSP_ALTITUDE'])
            cursor_msg = ""
            last_loop_time = last_slow_msg_time = last_cycleTime = time.time()

            while True:
                    start_time = time.time()
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
                            print(board.RC['channels'])

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

