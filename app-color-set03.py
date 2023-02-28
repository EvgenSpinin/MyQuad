from flask import Flask, render_template, Response, request
import cv2
import threading
import time
import argparse
from yamspy import MSPy
import curses
from collections import deque
from itertools import cycle
import numpy as np


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
    global bat, alt, RCx, RCyaw, RCtrotle, RCpitch, RCroll
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

            # Выделяем область размером 10x10 пикселей для извлечения цветовых характеристик
            roi = frame[100:110, 100:110]

            # Переводим область в цветовое пространство HSV
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

            # Вычисляем средние значения по каналам цвета
            h_mean, s_mean, v_mean = cv2.mean(hsv_roi)[:3]

           # Задаем диапазон для поиска цветового объекта
            lower_color = np.array([h_mean - 10, s_mean - 50, v_mean - 50])
            upper_color = np.array([h_mean + 10, s_mean + 50, v_mean + 50])

            # еслинажать на кнопку , фиксируем цвет по которому будем искать обьекти и переводим переменную
            # в режим зафиксировано
            if RCx > 1700:
                fixcont = 1
                lower_color_set = lower_color
                upper_color_set = upper_color

            # Ищем объекты по цвету
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            if fixcont == 1:
                binary = cv2.inRange(hsv, lower_color_set, upper_color_set)
            else: 
                binary = cv2.inRange(hsv, lower_color, upper_color)

           # создаем цвет в формате HSV ДЛЯ ВІРИСОВКИ ОБРАЗЦА ЦВЕТА ЗАХВАТА
            hsv_color = np.array([[[h_mean,s_mean,v_mean]]], dtype=np.uint8)
           # преобразуем цвет из формата HSV в BGR
            bgr_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2BGR)

            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)  # получаем контуры выделенных областей


            if len(contours) != 0:  # если найден хоть один контур

                #if fixcont == 
                maxc = max(contours, key=cv2.contourArea)  # находим наибольший контур

                moments = cv2.moments(maxc)  # получаем моменты этого контура

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


            if iSee:    # если был найден объект
                controlY = controlY
            else:
                controlY = 0.0  # останавливаемся
                controlX = 0.0  # сбрасываем меру поворота


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

            if fixcont == 1:
               cv2.putText(frame, 'FIXED: {}'.format(text), (width - 70, height - 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.23, (0, 0, 240), 1, cv2.LINE_AA)  # добавляем поверх кадра текст
 
             # Отображаем изображение с выделенной областью и рассчитанным диапазоном цвета
            cv2.rectangle(frame, (100, 100), (110, 110), (0, 255, 0), 1)
            cv2.putText(frame, f"Color Range: {lower_color} - {upper_color}", (10, 30),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 2)

            cv2.circle(frame, (300,200), 20, bgr_color[0, 0].tolist(), -1)

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
            slow_msgs = cycle(['MSP_ANALOG', 'MSP_MOTOR', 'MSP_RC', 'MSP_ALTITUDE'])
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

                        #elif next_msg == 'MSP_STATUS_EX':
                            #print(board.process_mode(board.CONFIG['mode']))
                            #print("Flight Mode: {}".format(board.process_mode(board.CONFIG['mode'])))

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

