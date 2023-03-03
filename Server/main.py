#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import gi
import boto3
import argparse

boto3.setup_default_session(region_name='eu-west-2')

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GstRtsp, GObject, GLib

# getting the required information from the user
parser = argparse.ArgumentParser()
parser.add_argument("--port", default=8554, help="port to stream video", type=int)
parser.add_argument("--stream_uri", required=True, help="endpoint you'd like to host on. i.e. <domain_name>/<endpoint>")
parser.add_argument("--debug", help="The desired level of debug output, can be 0, 1 or 2", default=1, type=int)
opt = parser.parse_args()

Gst.init(None)
Gloop = GLib.MainLoop()

endpoints = opt.stream_uri.split(",")

# Sensor Factory class which inherits the GstRtspServer base class and add
# properties to it.
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)
        self.device_id = None
        print("Init")

    def do_create_element(self, url):
        request_uri = url.get_request_uri()
        print('[INFO]: stream request on {}'.format(request_uri))

        # queue2 is better if network speed is a concern
        launch_string = "filesrc location={} ! " \
                        "qtdemux ! " \
                        "h264parse ! " \
                        "queue2 ! " \
                        "rtph264pay name=pay0 config-interval=1 pt=96".format(video_map[self.device_id])
        player = Gst.parse_launch(launch_string)

        self.video_length = int(get_length(video_map[self.device_id]))
        if int(opt.debug) >= 1:
            print("Video Length: " + str(self.video_length))

        # creates extended Gst.Bin with message debugging enabled
        self.extendedBin = ExtendedBin()
        self.extendedBin.fake_init(self.video_length, self.device_id)
        self.extendedBin.add(player)

        # creates new Pipeline and adds extended Bin to it
        self.extendedPlayer = Gst.Pipeline.new("extendedPipeline")
        self.extendedPlayer.add(self.extendedBin)
        self.extendedBin.set_player(self.extendedPlayer)

        return self.extendedPlayer

    # attaching the source element to the rtsp media
    def do_configure(self, rtsp_media):
        self.rtsp_media = rtsp_media
        # rtsp_media.set_protocols(GstRtsp.RTSPLowerTrans.TCP)  # Only stream via TCP
        rtsp_media.set_shared(True)
        print('[INFO]: Configure request on {}'.format(self.device_id))
        rtsp_media.set_do_retransmission(False)


# Rtsp server implementation where we attach the factory sensor with the stream uri
class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory()
        print("GSTSERVER RUNNING")
        self.set_service(str(opt.port))
        self.attach(None)

    def add_source(self, device_id):
        factory = SensorFactory()
        factory.device_id = device_id
        self.get_mount_points().add_factory("/" + device_id, factory)

# extended Gst.Bin that overrides do_handle_message and adds debugging
class ExtendedBin(Gst.Bin):

    def fake_init(self, length, endpoint):
        self.video_length = length - 1  # -1 for some buffer (the video pauses at the EOS
        self.endpoint = endpoint

    def set_player(self, player):
        self.my_player = player


    def do_handle_message(self, message):

        if int(opt.debug) >= 2:

            if message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                print("ERROR:", message.src.get_name(), ":", error.message)
                if debug:
                    print ("Debug info: " + debug)

            elif message.type == Gst.MessageType.EOS:
                print ("End of stream")

            elif message.type == Gst.MessageType.STATE_CHANGED:
                oldState, newState, pendingState = message.parse_state_changed()
                print ("State changed -> old:{}, new:{}, pending:{}".format(oldState, newState, pendingState))

            elif message.type == Gst.MessageType.STREAM_STATUS:
                incoming, owner = message.parse_stream_status()
                print ("message: {} Owner: {}".format(incoming, owner))

            else :
                print("Some other message type: " + str(message.type))

        if message.type == Gst.MessageType.STREAM_STATUS:
            incoming, owner = message.parse_stream_status()
            if incoming == Gst.StreamStatusType.LEAVE or incoming == Gst.StreamStatusType.DESTROY:
                if int(opt.debug) >= 2:
                    print("Stream shutting down")
                # Keeping this as a seperate if in case you want to do some cleanup...

        if message.type == Gst.MessageType.DURATION_CHANGED: # Called when stream has started
            print("Duration changed")
            GLib.timeout_add(25, self.seek_video) # Call the seek after the video has begun playing

        if message.type == Gst.MessageType.SEGMENT_DONE:
            self.seek_video()

        Gst.Bin.do_handle_message(self, message)

    def set_pid(self, pid):
        if int(opt.debug) >= 1:
            print("Adding PID: " + str(pid))
        self.pid = pid

    def seek_video(self):
        if opt.debug >= 1:
            print("Seeking...")
        self.my_player.seek(1.0,
              Gst.Format.TIME,
              Gst.SeekFlags.SEGMENT,
              Gst.SeekType.SET, 0,
              Gst.SeekType.SET, self.video_length * Gst.SECOND)

def get_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)


video_map = {"test": "sample-5s.mp4"}

def start_RTSP():
    # initializing the threads and running the stream on loop.
    endpoints = opt.stream_uri.split(",")
    server = GstServer()

    for endpoint in endpoints:
        server.add_source(endpoint)
        print(f"--------------------------- STREAMING BEGUN AT /{endpoint} ------------------------------------")

    Gloop.run()


start_RTSP()