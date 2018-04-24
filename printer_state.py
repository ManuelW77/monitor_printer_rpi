#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import paho.mqtt.client as mqtt
import Adafruit_GPIO.SPI as SPI
import json
import requests
import Adafruit_SSD1306
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont
from neopixel import *


# Octoprint API
octoApi = "944145C8AF374B77B6D66BD88C410C1D"

# Definition Display / Pin 3 (SDA) und 5 (SCL)
RST = 24
disp = Adafruit_SSD1306.SSD1306_128_64(rst=RST)

# Definition LED
LED_COUNT = 33      # Number of LED pixels.
LED_PIN = 18      # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10  # 5       # DMA channel to use for generating signal (try 5)
LED_INVERT = False   # True to invert the signal (when using NPN transistor level shift)
LED_BRIGHTNESS = 255  # Helligkeit gesamt

# Definition Relais Pinout
rPin1 = 6  # Licht
rPin2 = 13  # Bordfan
rPin3 = 19  # Bedfan
rPin4 = 26  # leer

# Button Pins
bPinStartStop = 17  # Start Stop Print
bPinPauseResume = 27  # Pause Resume Print
bPinExtrude = 22  # Extrude Filament
bExtrusionWide = 50  # mm to extrude
bPinEmergency = 18  # Notaus

bLEDStartStop = 23  # Led für Start Stop
bLEDPauseResume = 24  # Pause Resume LED
bLEDExtrude = 10  # Extrusion LED
bLEDEmergency = 9  # Emergency LED

# Debug
debug = False

# Druckstatus
pState = False
printDone = False
printerOn = False
lastPercent = -1
bed_data = [0, 0]
tool0_data = [0, 0]
last_t = 0

# GPIO als OUTPUT setzen
GPIO.setmode(GPIO.BCM)
GPIO.setup(rPin1, GPIO.OUT)
GPIO.setup(rPin2, GPIO.OUT)
GPIO.setup(rPin3, GPIO.OUT)
GPIO.setup(rPin4, GPIO.OUT)

# GPIO für Button aktivieren
GPIO.setup(bPinStartStop, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(bPinPauseResume, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(bPinExtrude, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(bPinEmergency, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# GPIO für LEDs setzen
GPIO.setup(bLEDStartStop, GPIO.OUT)
GPIO.setup(bLEDPauseResume, GPIO.OUT)
GPIO.setup(bLEDExtrude, GPIO.OUT)
GPIO.setup(bLEDEmergency, GPIO.OUT)

# GPIO für LEDs auf OFF setzen
GPIO.setup(bLEDStartStop, GPIO.HIGH)
GPIO.setup(bLEDPauseResume, GPIO.HIGH)
GPIO.setup(bLEDExtrude, GPIO.HIGH)
GPIO.setup(bLEDEmergency, GPIO.HIGH)

# Alle Relais auf OFF setzen
GPIO.output(rPin1, GPIO.HIGH)
GPIO.output(rPin2, GPIO.HIGH)
GPIO.output(rPin3, GPIO.HIGH)
GPIO.output(rPin4, GPIO.HIGH)

# Start Display
disp.begin()
width = disp.width
height = disp.height
disp.clear()
disp.display()

# Display Welcome Message
image = Image.new('1', (width, height))

# Alternatively load a TTF font.  Make sure the .ttf font file is in the same directory as the python script!
# Some other nice fonts to try: http://www.dafont.com/bitmap.php
# font = ImageFont.truetype('Minecraftia.ttf', 8)
# font = ImageFont.load_default()
font16 = ImageFont.truetype('/home/pi/printer_state.ttf', 15)
font8 = ImageFont.truetype('/home/pi/printer_state.ttf', 10)
draw = ImageDraw.Draw(image)

# Start LED Strip
strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS)
strip.begin()


def colorWipe(strip, color, wait_ms=50):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
        strip.show()
        time.sleep(wait_ms/1000.0)


def ledStartWipe(color, wait_ms=50):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
        strip.show()
        time.sleep(wait_ms/1000.0)

    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0,))
        strip.show()
        time.sleep(wait_ms/1000.0)

    for i in range(strip.numPixels(), -1, -1):
        strip.setPixelColor(i, color)
        strip.show()
        time.sleep(wait_ms/1000.0)

    for i in range(strip.numPixels(), -1, -1):
        strip.setPixelColor(i, Color(0, 0, 0,))
        strip.show()
        time.sleep(wait_ms/1000.0)


def ledPrintState(c, wait_ms=50):
    state = int(strip.numPixels()*c/100)
    if state == 0:
        state = 1

    if debug is True:
        print "Show ledPrintState -> " + str(c) + "% -> LED " + str(state)
        print "------------"

    for i in range(0, state):
        # bei 50% (von 33 LEDs) / rot
        if (i < 16):
            strip.setPixelColor(i, Color(0, 255, 0))

        # 50% - 75% / orange
        elif (i >= 16 and i < 24):
            strip.setPixelColor(i, Color(90, 255, 0))

        # 75% - 90% / gelb
        elif (i >= 24 and i < 29):
            strip.setPixelColor(i, Color(255, 255, 0))

        # 90% - 95% / hellgrün
        elif (i >= 29 and i < 31):
            strip.setPixelColor(i, Color(212, 201, 0))

        # Rest grün
        else:
            strip.setPixelColor(i, Color(255, 0, 0))

        strip.show()
        time.sleep(wait_ms/1000.0)


def ledHeatingState(data):
    global last_t

    # c = current, t = target
    c = data[0]
    t = data[1]

    if debug is True:
        print "Show ledHeatingState -> " + str(c) + " | " + str(t)
        print "----------"

    if c > 0:
        if t == 0 and last_t == 0:
            last_t = 210  # c

        elif t > 0:
            last_t = t

        # led = Prozent der Zieltemp erreicht
        led = int(c * 100.0 / last_t)
        # led = Anzahl der zu läuchtenden LEDs
        led = int(led * strip.numPixels() / 100)

    else:
        led = 0

    for i in range(0, led):
        if (i < 10):
            strip.setPixelColor(i, Color(255, 0, 0))

        elif (i >= 10 and i < 29):
            strip.setPixelColor(i, Color(90, 255, 0))

        elif (i >= 29 and c < 180):
            strip.setPixelColor(i, Color(45, 255, 0))

        elif (i >= 29 and c >= 180):
            strip.setPixelColor(i, Color(0, 255, 0))

        strip.show()

    # alle Pixel größer led ausschalten
    for i in range(led, strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()


def fitNumbers3(number):
    if number < 10:
        number = "   " + str(number)
    elif number > 10 and number < 100:
        number = "  " + str(number)

    return str(number)


def displayPrintState(what, data):
    global width, height

    '''
    Gelber Bereich Reihe 0 - 15
    Leerer Bereich Reihe 16
    Blauer Bereich Reihe 17 - 64
    '''

    if debug is True:
        print "Show displayPrintState -> " + what
        print "----------"

    # Trennlinie
    draw.rectangle((0, 13, 128, 15), outline=0, fill=1)

    if what == "progress":
        global pPercent

        pPercent = data[1]

        # File
        draw.rectangle((0, 17, width, 26), outline=0, fill=0)  # clean
        draw.text((0, 17), data[0], font=font8, fill=255)

    if what == "tool0":
        draw.rectangle((0, 27, width, 45), outline=0, fill=0)  # clean
        draw.text((0, 31), "Tool " + fitNumbers3(data[0]) + " | " + fitNumbers3(data[1]) + " C", font=font16, fill=255)

    if what == "bed":
        draw.rectangle((0, 46, width, 64), outline=0, fill=0)  # clean
        draw.text((0, 46), " Bed " + fitNumbers3(data[0]) + " | " + fitNumbers3(data[1]) + " C", font=font16, fill=255)

    disp.image(image)
    disp.display()


def clearAll():
    global width, height  # Display Data

    if debug is True:
        print "Clear Display and Strip"
        print "----------"

    colorWipe(strip, Color(0, 0, 255))

    draw.rectangle((0, 0, width, height), outline=0, fill=0)  # clean
    disp.image(image)
    disp.display()


def powerOffAll():
    if debug is True:
        print "Power OFF all!"
        print "----------"

    colorWipe(strip, Color(0, 0, 0))
    draw.rectangle((0, 0, width, height), outline=0, fill=0)  # clean
    disp.image(image)
    disp.display()


def powerOnAll():
    if debug is True:
        print "Power ON all!"
        print "----------"

    # Display Welcome Message
    draw.text((20, 0), "Willkommen ...", font=font16, fill=255)
    draw.text((35, 20), "Tronxy", font=font16, fill=255)
    draw.text((44, 40), "X5S", font=font16, fill=255)

    disp.image(image)
    disp.display()

    # Color Wipe auf LED Strip abspielen
    colorWipe(strip, Color(255, 0, 0))


def boardFanOff():
    if debug is True:
        print "Board Fan off"
        print "----------"

    # Board Fan off
    GPIO.output(rPin2, GPIO.HIGH)


def bedFanOff():
    if debug is True:
        print "Bed Fan off"
        print "----------"

    # Bed Fan off
    GPIO.output(rPin3, GPIO.HIGH)


def getApiData(api):
    # RestAPI
    url = "http://localhost/api/job"
    headers = {"X-Api-Key": api, "Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers)
        printTime = response.json()["progress"]["printTime"]
        printTimeLeft = response.json()["progress"]["printTimeLeft"]

        if debug is True:
            print "API Abfrage erfolgreich"
            print "----------"

    except BaseException:
        if debug is True:
            print "Fehler beim Abfrage den API"
            print "----------"

    if printTime is None:
        printTime = 0

    if printTimeLeft is None:
        printTimeLeft = 0

    return printTime, printTimeLeft


def is_json(myjson):
    try:
        json_object = json.loads(myjson)
    except ValueError, e:
        return False
    return True


def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    client.subscribe("octoprint/#")


def on_message(client, userdata, msg):
    global width, height  # Display Data
    global pState, printDone, lastPercent  # Druckstatus
    global bed_data, tool0_data, printerOn

    if is_json(msg.payload) is True:
        output = json.loads(msg.payload)

        if debug is True:
            print "Message arrived: [" + msg.topic + "]: " + str(output)
            print "----------"

        # On shut printer off
        if "power" in msg.topic:
            if output["power"] == "off":
                powerOffAll()
                printerOn = False

            elif output["power"] == "on":
                powerOnAll()
                printerOn = True

        # setze Drucker auf ein, wenn ein Druck bereits läuft
        if printerOn is False and "progress/printing" in msg.topic:
            printerOn = True

        # Wenn Drucker eingeschaltet ist
        if printerOn is True:
            # Aktionen nach Topic aufteilen
            # Druckstart
            if "PrintStarted" in msg.topic:
                if debug is True:
                    print "Print Started"
                    print "----------"

                pState = True
                printDone = False
                clearAll()

                path = output["path"].replace(".gcode", "")
                # Displayausgabe
                data = [path, 0]
                displayPrintState("progress", data)
                # LED Ausgabe
                ledStartWipe(Color(0, 0, 255))
                ledPrintState(0)

            # Druckende
            elif "PrintDone" in msg.topic or "PrintCancelled" in msg.topic or "PrintFailed" in msg.topic:
                if "PrintDone" in msg.topic:
                    path = "Print Done..."

                    if debug is True:
                        print "Print Done..."
                        print "----------"

                elif "PrintCancelled" in msg.topic:
                    path = "Print Cancelled..."

                    if debug is True:
                        print "Print Cancelled..."
                        print "----------"

                else:
                    path = "Print Failed..."

                    if debug is True:
                        print "Print Failed..."
                        print "----------"

                # Displayausgabe
                data = [path, 0]
                displayPrintState("progress", data)

                pState = False
                printDone = True
                boardFanOff()

            # Info über Druck
            elif "progress/printing" in msg.topic:
                if debug is True:
                    print "Progress Update Message"
                    print "----------"

                '''
                if lastPercent < output["progress"] and output["progress"] != 100 and pState is False:
                    if debug is True:
                        print "Starte Druckinfo im bereits laufenden Druck"
                        print "----------"

                    pState = True
                    clearAll()
                '''

                if pState is True:
                    if debug is True:
                        print "is Printing..."
                        print "----------"

                    path = output["path"].replace(".gcode", "")

                    if output["progress"] != lastPercent:
                        # Displayausgabe
                        data = [path, output["progress"]]
                        displayPrintState("progress", data)
                        # LED Ausgabe
                        ledPrintState(output["progress"])

                else:
                    if debug is True:
                        print "is not Printing..."
                        print "----------"

                    path = "Not printing..."

                lastPercent = output["progress"]

            # Hotend
            elif "tool0" in msg.topic:
                if debug is True:
                    print "Tool0 Update Message"
                    print "----------"

                tool0_data = [int(output["actual"]), int(output["target"])]
                # Displayausgabe
                displayPrintState("tool0", tool0_data)

                # LED Ausgabe, wenn kein Druck läuft zeige Temp sonst Prozent
                if pState is False:
                    ledHeatingState(tool0_data)
                else:
                    ledPrintState(lastPercent)

            # Bed
            elif "bed" in msg.topic:
                if debug is True:
                    print "Bed Update Message"
                    print "----------"

                bed_data = [int(output["actual"]), int(output["target"])]
                displayPrintState("bed", bed_data)

                if int(output["actual"]) < 38 and int(output["target"]) == 0 and pState is False:
                    bedFanOff()

                    if debug is True:
                        print "Switch Bedfan OFF"
                        print "----------"

            # On Error or Disconnect Shut Off
            elif "Error" in msg.topic or "Disconnect" in msg.topic:
                if debug is True:
                    print "Error happens while printing"
                    print "----------"

                client.publish("esp_tronxy_pow/relay/0/set", "0")

            '''
            else:
                if debug is True:
                    print "undefined Message..."
                    print "----------"
            '''

            # Alles ausschalten nach Druck und wenn unter Temps
            if printDone is True:
                if debug is True:
                    print "Watch for Power Off ----> Druckt: " + str(pState) + " Done: " + str(printDone) + " - " + str(tool0_data[0]) + " - " + str(bed_data[0])
                    print "----------"

            if pState is False and printDone is True and tool0_data[0] < 35 and tool0_data[1] == 0 and bed_data[0] < 35 and bed_data[1] == 0:
                powerOffAll()
                client.publish("esp_tronxy_pow/relay/0/set", "0")
                printDone = False


def getPrintTime(pt):
    # Zeit in Minuten
    printTime = int(pt / 60)

    # Zeit in Stunden wenn größer 60min
    if printTime > 60:
        h = 0
        while printTime > 60:
            h += 1
            printTime = printTime-60

        if printTime < 10:
            printTime = "0" + str(printTime)

        printTime = str(h) + ":" + str(printTime) + "h"

    else:
        printTime = str(printTime) + "min"

    # wenn wenige als 1min
    if printTime < 1:
        printTime = "< 1min"

    return printTime


def buttonLedBlink(led, duration):
    while True:
        GPIO.setup(led, GPIO.LOW)
        time.sleep(50)
        GPIO.setup(led, GPIO.HIGH)
        time.sleep(50)


def buttonCommandLed(command):
    '''
    bLEDStartStop = 23  # Led für Start Stop
    bLEDPauseResume = 24  # Pause Resume LED
    bLEDExtrude = 10  # Extrusion LED
    bLEDEmergency = 9  # Emergency LED
    '''
    
    # Start Stop
    if command == "cancel":
        GPIO.setup(bLEDStartStop, GPIO.HIGH)
    
    if command == "start":
        GPIO.setup(bLEDStartStop, GPIO.LOW)
    
    # Pause Resume
    if command == "pause":
        # buttonLedBlink("bLEDPauseResume")
        GPIO.setup(bLEDPauseResume, GPIO.HIGH)
    
    if command == "resume":
        GPIO.setup(bLEDPauseResume, GPIO.LOW)
    
    # Extrudieren
    if command == "extrude":
        GPIO.setup(bLEDExtrude, GPIO.LOW)
    
    # Emergency Stop
    if command == "emergency":
        GPIO.setup(bLEDEmergency, GPIO.LOW)


def sendButtonCommand(api, button, printing):
    global tool0_data, bExtrusionWide, pState, printDone

    headers = {'X-Api-Key': api, "Content-Type": "application/json"}

    if button == "StartStop":
        time.sleep(0.2)
        if printing is True:
                print "Stopping printing"
                contents = json.dumps({"command": "cancel"})
                buttonCommandLed("cancel")
        else:
                print "Starting printing"
                contents = json.dumps({"command": "start"})
                buttonCommandLed("start")

        url = 'http://localhost/api/job'
        requests.post(url, data=contents, headers=headers)
    
    if button == "PauseResume":
        time.sleep(0.2)
        if printing is True:
            if debug is True:
                print "Pause printing"
            contents = json.dumps({"command": "pause"})
            buttonCommandLed("pause")
        else:
            if debug is True:
                print "Resume printing"
            contents = json.dumps({"command": "resume"})
            buttonCommandLed("resume")

        url = 'http://localhost/api/job'
        requests.post(url, data=contents, headers=headers)
    
    if button == "Extrude":
        time.sleep(0.2)
        if printing is False and tool0_data[1] > 180:
            if debug is True:
                print "Extrude Filament"

            contents = json.dumps({"command": "extrude", "amount": bExtrusionWide})
            url = 'http://localhost/api/printer/tool'
            requests.post(url, data=contents, headers=headers)
            buttonCommandLed("extrude")
                
        else:
            if debug is True:
                print "Is printing or Tool Temp < 180"

    if button == "Emergency":
        if debug is True:
            print "Emergency Button pressed"

        powerOffAll()
        client.publish("esp_tronxy_pow/relay/0/set", "0")
        printDone = False
        buttonCommandLed("emergency")


# Start MQTT
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("192.168.1.5", 1883, 60)
client.loop_start()

try:
    lastTime = 0
    pPercent = 0
    displayPrintTime = False
    bEmergencyTime = 0

    while True:
        # Auf Buttons lauschen
        # bPinStartStop = 17  # Start Stop Print
        # bPinPauseResume = 27  # Pause Resume Print
        # bPinExtrude = 22  # Extrude Filament
        # bExtrusionWide = 50  # mm to extrude
        # bPinEmergency = 18  # Notaus
        bPinStartStop_state = GPIO.input(bPinStartStop)
        bPinPauseResume_state = GPIO.input(bPinPauseResume)
        bPinExtrude_state = GPIO.input(bPinExtrude)
        bPinEmergency_state = GPIO.input(bPinEmergency)

        if bPinStartStop_state is False:
            sendButtonCommand(octoApi, "StartStop", pState)

        if bPinPauseResume_state is False:
            sendButtonCommand(octoApi, "PauseResume", pState)

        if bPinExtrude_state is False:
            sendButtonCommand(octoApi, "Extrude", pState)

        if bPinEmergency_state is False:
            bEmergencyTime += 1
            
            if bEmergencyTime == 5:
                sendButtonCommand(octoApi, "Emergency", pState)
        else:
            bEmergencyTime = 0

        # Wenn ein Druck läuft aller 15sek Anzeige wechseln
        if pState is True and (time.time()-lastTime > 15 or lastTime == 0):
            if debug is True:
                print "lastTime = 0 or 5sek left (printing: " + str(pState) + ")"
                print "----------"

            lastTime = time.time()

            draw.rectangle((0, 0, width, 12), outline=0, fill=0)  # clean

            if displayPrintTime is True:
                displayPrintTime = False

                # Hole Druckzeiten per RestAPI
                pTime, pTimeLeft = getApiData(octoApi)

                draw.text((0, 0), "D: " + getPrintTime(pTime) + " | L: " + getPrintTime(pTimeLeft), font=font16, fill=255)

                if debug is True:
                    print "D: " + getPrintTime(pTime) + " | L: " + getPrintTime(pTimeLeft)
                    print "----------"

            else:
                displayPrintTime = True

                # Prozentbalken
                draw.rectangle((0, 0, 89, 11), outline=1, fill=0)
                draw.rectangle((0, 0, int(88.0/100*pPercent), 11), outline=1, fill=1)

                # Prozentanzeige
                draw.text((91, 0), str(pPercent) + "%", font=font16, fill=255)

            disp.image(image)
            disp.display()

        # Programm 1s schlafen lassen
        # time.sleep(1)

except KeyboardInterrupt:
    print "Good Bye"
    print "----------"
    powerOffAll()

'''
except BaseException:
    print "Sonstiger Fehler !!!"
    draw.rectangle((0, 0, width, height), outline=0, fill=0)  # clean
    disp.image(image)
    disp.display()
'''
