"""

Kod till en automatisk rullgardin, skriven för att köras med en esp32 flashad med micropython
Kommando för att köra med ampy: ampy -p COM8 -b 115200 --delay 3 run .\totalo.py 

"""

import machine
import utime as time
import ntptime
import network
import uasyncio as asyncio

SSID = "ditt_wifi_ssid"
PASSWORD = "ditt_wifi_password"

# Pins
upPin = machine.Pin(27, machine.Pin.OUT)
downPin = machine.Pin(23, machine.Pin.OUT)
buttonPin = machine.Pin(4, machine.Pin.IN)

# Vars
upTime, downTime = None, None
setupState = False
upDownState = None

def activateBlinds(way):
    pin = upPin if way == "up" else downPin
    duration = upTime if way == "up" else downTime

    print(f"Rolling {way}...")
    pin.on()
    time.sleep(duration)
    pin.off()
    print(f"Blinds fully rolled {way}")

    return way

def connectToWifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)  # create station interface
    wlan.active(True)  # activate the interface

    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            print("Connecting...")
            pass

    if wlan.isconnected(): print("Connected to WiFi")
    
    ip_address = wlan.ifconfig()[0]  # Get the IPv4 address
    print("IPv4 Address:", ip_address)
    
    return ip_address

async def handleRequest(reader, writer):
    if setupState == False:
        print("Setup not yet completed")
        return
                
    request = await reader.read(1024)
    global upTime, downTime

    if request:
        request_str = request.decode("utf-8")
        method, path, *_ = request_str.split(" ")

        if method == "GET":
            if path == "/up":
                # AKTIVERA UPP RULLNING
                print("/up")
                print(upPin, upTime)
                activateBlinds("up")
                writer.write("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nRullar upp...")
            elif path == "/down":
                # AKTIVERA NER RULLNING
                print("/down")
                print(downPin, downTime)
                activateBlinds("down")
                writer.write("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nRullar ner...")
            else:
                print("Unknown request")
                writer.write("HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\n404 Not Found")
        
        await writer.drain()

    writer.close()
    await writer.wait_closed()

def pressToContinue(pin):
    previousValue = pin.value()
    while True:
        if pin.value() == 1 and previousValue == 0:
            return
        previousValue = pin.value()
        pass

def setup():
    def timing(pin):
        startTime = time.time()
        pin.on()
        print(f"Press button when blinds are fully {"down" if pin == downPin else "up"}...")

        previousValue = buttonPin.value()
        while True:
            if buttonPin.value() == 1 and previousValue == 0:
                pin.off()
                break
            previousValue = buttonPin.value()
        
        # Om problem --> möjligt med "while buttonPin.value() == 0" istället för "while True"
        endTime = time.time()
        return endTime - startTime

    # DOWN
    print("Press button to beging setup...")
    pressToContinue(buttonPin)

    print("Rolling down...")
    downTime = timing(downPin)
    print(f"Took {downTime} seconds for the blinds to roll down \n")

    # UP
    print("Press button again to proceed... ")
    pressToContinue(buttonPin)

    print("Rolling up...")
    upTime = timing(upPin)
    print(f"Took {upTime} seconds for the blinds to roll up")

    print("Setup completed successfully \n")
    return downTime, upTime

async def motorMain():
    # Uppdatera esp32'ans interna klocka så den går korrekt (annars fast på år 2000)
    try:
        ntptime.settime()
        print("Time updated from NTP server.")
    except Exception as e:
        print("Failed to update time from NTP server:", str(e))

    global upDownState
    global downTime
    global upTime
    global setupState
    wakeupTime = "18:24"
    sleepTime = "22:00"
    previousValue = None

    while True:
        now = time.localtime()
        curTime = "{:02}:{:02}".format(now[3], now[4])

        # print(buttonPin.value())

        # Setup for blinds
        if downTime is None or upTime is None:
            if buttonPin.value() == 1:
                print("Setting up blinds...")
                downTime, upTime = setup()
                setupState = True
                upDownState = "up"

        # print(setupState, previousValue)

        if setupState and previousValue == 0:
            # Single press activation
            if buttonPin.value() == 1:
                if upDownState == "down":
                    upDownState = activateBlinds("up")
                    buttonPin.value(0)
                    continue
                elif upDownState == "up":
                    upDownState = activateBlinds("down")
                    buttonPin.value(0)
                    continue

            # Time controlled activation
            if wakeupTime == curTime and upDownState == "down":
                upDownState = activateBlinds("up")
                print("WAKEY WAKEY")
                time.sleep_ms(5000)
                continue
            
            if sleepTime == curTime and upDownState == "up":
                upDownState = activateBlinds("down")
                print("SLEEPY TIME")
                time.sleep_ms(5000)
                continue

        # Avslutande i loopen för att undvika timeout och spara föregående button value
        previousValue = buttonPin.value()    
        print("Listening for manual input")
        await asyncio.sleep(0.1)

async def main(WIFI_SSID, WIFI_PASSWORD):
    # Connect to WiFi
    try:
        ipAddress = connectToWifi(WIFI_SSID, WIFI_PASSWORD)
    except Exception as e:
        print("Could not connect to WiFi: " + str(e))
        return

    # HTTP server setup
    PORT = 8080

    server = await asyncio.start_server(lambda r, w: handleRequest(r, w), ipAddress, PORT)
    print(f"Server started on {ipAddress}:{PORT}")

    # Loop for manual input
    asyncio.create_task(motorMain())

    async with server:
        while True:
            print("Listening for incoming requests...")
            await asyncio.sleep(0.2)

if __name__ == "__main__":
    asyncio.run(main(SSID, PASSWORD))