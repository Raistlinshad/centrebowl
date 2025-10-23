#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ball Sensor Daemon - Runs in separate process with minimal overhead
Communicates with main game via Unix domain socket (line-delimited JSON), and
optionally via multiprocessing.Queue when started from Python.
"""

import RPi.GPIO as GPIO
import time
import json
import os
import signal
import sys
import socket
import select
import logging
from multiprocessing import Queue, Process

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger('BallSensorDaemon')

# Unix socket path
SOCKET_PATH = '/tmp/ball_sensor.sock'


class BallSensorDaemon:
    """Runs in separate process - minimal overhead"""

    def __init__(self, gpio_pin, detection_queue=None, control_queue=None, socket_path=SOCKET_PATH):
        """
gpio_pin: GPIO pin number for ball sensor
detection_queue: optional multiprocessing Queue to send detections to main process
control_queue: optional queue to receive suspend/resume commands
socket_path: unix domain socket path used to talk to external clients (C++)
"""
        self.gpio_pin = gpio_pin
        self.detection_queue = detection_queue
        self.control_queue = control_queue
        self.socket_path = socket_path

        self.running = False
        self.suspended = False
        self.last_detection_time = None
        self.debounce_ms = 500  # 500ms debounce - prevents multiple detections from single ball pass

        # socket server state
        self.server_socket = None
        self.client_socket = None

    def setup(self):
        """Initialize GPIO"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            logger.info(f"GPIO {self.gpio_pin} initialized")
        except Exception as e:
            logger.error(f"GPIO setup failed: {e}")
            raise

    def _start_socket_server(self):
        """Create a unix domain socket server (single client). Remove stale socket if present."""
        # ensure old socket removed
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        except OSError:
            pass

        serv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        serv.setblocking(False)
        serv.bind(self.socket_path)
        serv.listen(1)
        logger.info(f"Socket server listening at {self.socket_path}")
        self.server_socket = serv

    def _send_to_client(self, data_str):
        """Send a line (newline-terminated) to connected client if present."""
        if not self.client_socket:
            return
        try:
            self.client_socket.sendall(data_str.encode('utf-8'))
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None

    def _forward_detection(self, payload):
        """Push payload dict into detection_queue if provided. Also send over socket to client as JSON line."""
        # push to queue (if set)
        if self.detection_queue:
            try:
                self.detection_queue.put(payload)
            except Exception as e:
                logger.debug(f"Failed putting into detection_queue: {e}")
        # always attempt to send to connected client
        try:
            line = json.dumps(payload) + "\n"
            self._send_to_client(line)
        except Exception as e:
            logger.debug(f"Failed to JSON/send detection: {e}")

    def _handle_client_command(self, line):
        """Interpret incoming commands from the socket client."""
        line = line.strip()
        if not line:
            return
        logger.info(f"Received command from client: {line}")
        # Simple textual commands:
        # LAST_BALL
        # PIN_SET <json array>
        if line == "LAST_BALL":
            # forward to detection queue as a control message
            payload = {'type': 'last_ball', 'timestamp': time.time()}
            self._forward_detection(payload)
        elif line.startswith("PIN_SET"):
            # expected: PIN_SET [1,2,3,...] or PIN_SET {"pins":[...]}
            rest = line[7:].strip()
            try:
                data = json.loads(rest)
                payload = {'type': 'pin_set'}
                if isinstance(data, dict):
                    payload.update(data)
                else:
                    payload['pins'] = data
                self._forward_detection(payload)
            except Exception as e:
                logger.error(f"Failed parsing PIN_SET payload: {e}")
        else:
            # Unknown command - you can extend here
            logger.debug(f"Unknown command: {line}")
            try:
                self._send_to_client(json.dumps({'type': 'ack', 'cmd': line}) + "\n")
            except:
                pass

    def run(self):
        """Main sensor loop - runs in separate process"""
        self.setup()
        self.running = True
        last_state = 0

        # Prepare socket server
        try:
            self._start_socket_server()
        except Exception as e:
            logger.error(f"Failed to start socket server: {e}")

        logger.info("Ball sensor daemon started")

        # We'll use select over GPIO poll + socket events. Socket is non-blocking; we don't wait on GPIO,
        # but we will occasionally call select to service incoming client connections and incoming commands.
        while self.running:
            try:
                # Poll GPIO quickly (tight loop)
                current_state = GPIO.input(self.gpio_pin)
                current_time = time.time()

                # Detect rising edge (LOW -> HIGH)
                if current_state == 1 and last_state == 0:
                    # Check debounce
                    if self.last_detection_time is None or \
                       (current_time - self.last_detection_time) * 1000 >= self.debounce_ms:

                        logger.info(f"Ball detected at {current_time}")
                        self.last_detection_time = current_time

                        # Send detection to main process / client
                        payload = {'type': 'ball_detected', 'timestamp': current_time}
                        self._forward_detection(payload)

                last_state = current_state

                # Handle socket accept/read using non-blocking select
                read_list = []
                if self.server_socket:
                    read_list.append(self.server_socket)
                if self.client_socket:
                    read_list.append(self.client_socket)

                if read_list:
                    r, _, _ = select.select(read_list, [], [], 0.001)  # short timeout
                    for s in r:
                        if s is self.server_socket:
                            try:
                                client, _ = self.server_socket.accept()
                                client.setblocking(False)
                                self.client_socket = client
                                logger.info("Client connected to ball sensor socket")
                            except Exception as e:
                                logger.debug(f"Accept failed: {e}")
                        elif s is self.client_socket:
                            try:
                                data = self.client_socket.recv(4096)
                                if not data:
                                    logger.info("Client disconnected")
                                    try:
                                        self.client_socket.close()
                                    except:
                                        pass
                                    self.client_socket = None
                                else:
                                    lines = data.decode('utf-8', errors='ignore').splitlines()
                                    for line in lines:
                                        self._handle_client_command(line)
                            except BlockingIOError:
                                pass
                            except Exception as e:
                                logger.error(f"Client read error: {e}")
                                try:
                                    self.client_socket.close()
                                except:
                                    pass
                                self.client_socket = None
                # NOTE: no sleep here for detection responsiveness; select has short timeout

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Sensor error: {e}")
                time.sleep(0.01)

        # Cleanup
        try:
            if self.client_socket:
                self.client_socket.close()
        except:
            pass
        try:
            if self.server_socket:
                self.server_socket.close()
        except:
            pass
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        except:
            pass

        GPIO.cleanup()
        logger.info("Ball sensor daemon stopped")

    def stop(self):
        """Stop the daemon"""
        self.running = False


# Global daemon reference for signal handling
daemon = None
detection_queue = None


def start_ball_sensor_daemon(gpio_pin):
    """Start the ball sensor in a separate process
    Returns: (Queue, process) - detection Queue may be None if not provided
    """
    global daemon, detection_queue

    detection_queue = Queue()
    daemon = BallSensorDaemon(gpio_pin, detection_queue)

    # Start daemon process
    process = Process(target=daemon.run, daemon=True)
    process.start()

    logger.info(f"Ball sensor daemon process started (PID: {process.pid})")

    return detection_queue, process


def signal_handler(signum, frame):
    """Handle shutdown gracefully""" 
    global daemon
    if daemon:
        daemon.stop()
    sys.exit(0)

if __name__ == '__main__':
    # Example standalone usage
    GPIO_PIN = 24

    signal.signal(signal.SIGINT, signal_handler)

    queue, process = start_ball_sensor_daemon(GPIO_PIN)

    logger.info("Listening for detections (press Ctrl+C to stop)...")

    try:
        while True:
            if not queue.empty():
                detection = queue.get()
                logger.info(f"Main process received: {detection}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        logger.info("Shutting down")
        process.terminate()
        process.join()
