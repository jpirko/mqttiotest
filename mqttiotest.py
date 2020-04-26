#!/bin/env python3

"""
Licensed under the GNU General Public License, version 2 as
published by the Free Software Foundation; see COPYING for details.
"""

__author__ = """
jiri@resnulli.us (Jiri Pirko)
"""

import argparse
import configparser
import os
from tkinter import *
import tkinter
import paho.mqtt.publish as publish
import paho
from urllib.parse import urlparse

class MQTTClient:
    def __init__(self, host, port, client_id, window):
        self._client = paho.mqtt.client.Client(client_id)
        self._client.on_connect = self.__on_connect
        self._client.on_disconnect = self.__on_disconnect
        self._client.on_message = self.__on_message
        self._client.connect_async(host, port)
        self._client.loop_start()
        self._window = window
        self._subscribers = dict()

    def __on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            return
        self._window.mqtt_status_set(True)
        for topic in self._subscribers.keys():
            self._client.subscribe(topic)

    def __on_disconnect(self, client, userdata, rc):
        self._window.mqtt_status_set(False)
        for topic in self._subscribers.keys():
            self._subscribers[topic]((None))
    
    def __on_message(self, client, userdata, msg):
        try:
            subscriber = self._subscribers[msg.topic]
        except:
            pass
        subscriber(msg.payload.decode())

    def subscriber_register(self, topic, subscriber):
        self._subscribers[topic] = subscriber

    def publish(self, topic, payload):
        ret, _ = self._client.publish(topic, payload)
        return True if ret == 0 else False
    
class Key:
    def __init__(self, key, topic, window, mqtt):
        row = self._parent.row_get()
        Label(self._parent, text=topic).grid(column=0, row=row, sticky=W, padx=5, pady=5)
        self._button = Button(self._parent, text=key, state=DISABLED, width=1)
        self._button.grid(column=1, row=row, sticky=W)
        window.bind('<KeyPress-{}>'.format(key), self.key_pressed)
        window.bind('<KeyRelease-{}>'.format(key), self.key_released)
        self._topic = topic
        self._mqtt = mqtt

    def state_set(self, state):
        relief = SUNKEN if state else RAISED
        if self._mqtt.publish(self._topic, int(state)):
            self._button.config(relief=relief)

class KeyButton(Key):
    def __init__(self, key, topic, window, mqtt):
        self._parent = window.buttons_frame
        super().__init__(key, topic, window, mqtt)
        self._window = window
        self._after_id = None

    def key_pressed(self, event):
        if self._after_id != None:
            self._window.after_cancel(self._after_id)
            self._after_id = None
            return
        self.state_set(True)
    
    def key_released(self, event):
        self._after_id = self._window.after_idle(self.process_released, event)
    
    def process_released(self, event):
        self._after_id = None
        self.state_set(False)

class KeySwitch(Key):
    def __init__(self, key, topic, window, mqtt):
        self._parent = window.switches_frame
        super().__init__(key, topic, window, mqtt)
        self._state = False

    def key_pressed(self, event):
        self._state = not self._state
        self.state_set(self._state)
    
    def key_released(self, event):
        pass

class Outlet:
    def __init__(self, topic, window, mqtt):
        self._parent = window.outlets_frame
        row = self._parent.row_get()
        Label(self._parent, text=topic).grid(column=0, row=row, sticky=W, padx=5, pady=5)
        self._value_str = tkinter.StringVar()
        self._value = Entry(self._parent, textvariable=self._value_str, state=DISABLED, width=10)
        self._value.grid(column=1, row=row, sticky=W)
        mqtt.subscriber_register(topic, self.__value_set)

    def __value_set(self, value):
        if value == "1":
            color = "green"
        elif value == "0":
            color = "red"
        else:
            color = "grey"
        self._value.config(disabledforeground=color)
        self._value_str.set(value if value else "")

class GroupFrame(LabelFrame):
    def __init__(self, window, name):
        super().__init__(window, text=name, relief=RIDGE, borderwidth=1)
        self._row = 0
    
    def row_get(self):
        self._row += 1
        return self._row

class Window(Tk):
    def __init__(self):
        super().__init__()
        self.bind('<Escape>', self.__close)
        
        status_frame = Frame(self)
        status_frame.grid(column=0, columnspan=3, row=0, sticky=W, padx=5, pady=5)
        Label(status_frame, text="MQTT broker state:").grid(column=0, row=0, sticky=W, padx=5, pady=5)
        self._mqtt_status_str = tkinter.StringVar()
        self._mqtt_status = Entry(status_frame, textvariable=self._mqtt_status_str, state=DISABLED, width=10)
        self._mqtt_status.grid(column=1, row=0, sticky=N+W)
        
        self.buttons_frame = GroupFrame(self, "Buttons")
        self.buttons_frame.grid(column=0, row=1, sticky=N+W, padx=5, pady=5)
        
        self.switches_frame = GroupFrame(self, "Switches")
        self.switches_frame.grid(column=1, row=1, sticky=N+W, padx=5, pady=5)
        
        self.outlets_frame = GroupFrame(self, "Outlets")
        self.outlets_frame.grid(column=2, row=1, sticky=N+W, padx=5, pady=5)
        
    def mqtt_status_set(self, status):
        self._mqtt_status.config(disabledforeground="green" if status else "red")
        self._mqtt_status_str.set("Connected" if status else "Disconnected")

    def __close(self, event):
        self.destroy()

def get_args():
    parser = argparse.ArgumentParser(prog="mqttiotest",
                                     description="MQTT client sending key events and receiving payload")
    parser.add_argument("-c", "--config", help="Configuration file.", required=True)
    return parser.parse_args()

class ConfigParser(configparser.ConfigParser):
    def get_uri(self, section, option, scheme, default_port):
        uri = self.get(section, option)
        pr = urlparse(uri)
        if pr.scheme != scheme or not pr.netloc or pr.path or pr.params or pr.query or pr.fragment:
            raise ValueError("\"{}\" format should be: \"{}://HOST[:PORT]\"".format(option, scheme))
        return pr.hostname, pr.port if pr.port else default_port

def main():
    args = get_args()

    config = ConfigParser(allow_no_value=True)
    config.read_file(open(os.path.abspath(args.config)))
    
    window = Window()
    window.geometry("400x300")
    window.title("MQTT button test")

    mqtt_host, mqtt_port = config.get_uri('main', 'mqtt_uri', 'mqtt', 1883)
    mqtt_client_id = config.get('main', 'mqtt_client_id')
    mqtt = MQTTClient(mqtt_host, mqtt_port, mqtt_client_id, window)

    for key, path in config.items("buttons"):
        KeyButton(key, path, window, mqtt)
    
    for key, path in config.items("switches"):
        KeySwitch(key, path, window, mqtt)
    
    for key, path in config.items("outlets"):
        Outlet(path, window, mqtt)

    window.mainloop()

if __name__ == '__main__':
    main()
